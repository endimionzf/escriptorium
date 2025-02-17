import json
import logging
from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Page, Paginator
from django.db import DataError, transaction
from django.db.models import Count, Q
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from easy_thumbnails.files import get_thumbnailer
from elasticsearch import exceptions as es_exceptions

from core.forms import (
    AlignForm,
    DocumentForm,
    DocumentOntologyForm,
    DocumentShareForm,
    FindAndReplaceForm,
    MetadataFormSet,
    MigrateDocumentForm,
    ModelRightsForm,
    ModelUploadForm,
    ProjectForm,
    ProjectShareForm,
    RecTrainForm,
    SearchForm,
    SegmentForm,
    SegTrainForm,
    TranscribeForm,
    UploadImageForm,
)
from core.models import (
    AlreadyProcessingException,
    Document,
    DocumentPart,
    Metadata,
    OcrModel,
    OcrModelDocument,
    OcrModelRight,
    Project,
)
from core.search import WORD_BY_WORD_SEARCH_MODE, build_highlighted_replacement_psql
from core.tasks import replace_line_transcriptions_text
from imports.forms import DocumentOntologyImportForm, ExportForm, ImportForm
from imports.serializers import OntologyImportSerializer
from reporting.models import TaskReport
from users.models import User

logger = logging.getLogger(__name__)


class PerPageMixin():
    paginate_by = 50
    MAX_PAGINATE_BY = 50
    PAGINATE_BY_CHOICES = [10, 20, 50]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['select_per_page'] = True
        context['paginate_by_choices'] = self.PAGINATE_BY_CHOICES
        return context

    def get_paginate_by(self, queryset):
        try:
            return min(int(self.request.GET.get("paginate_by", self.paginate_by)), self.MAX_PAGINATE_BY)
        except ValueError:
            return self.paginate_by


class Home(TemplateView):
    template_name = 'core/home.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['VERSION_DATE'] = settings.VERSION_DATE
        context['KRAKEN_VERSION'] = settings.KRAKEN_VERSION
        return context


class BaseSearch(LoginRequiredMixin, PerPageMixin, FormView, TemplateView):
    def get_form(self):
        self.form = self.form_class(self.request.GET, **self.get_form_kwargs())
        return self.form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user

        # We don't want potential POST data to reach the form
        if 'data' in kwargs:
            del kwargs['data']

        return kwargs

    @property
    def no_extra_calculation_condition(self):
        # No extra calculation if:
        # - the form is invalid
        # - the search terms are empty
        return not self.form.is_valid() or not self.form.cleaned_data.get('query')

    def get_line_viewbox(self, bounding_box):
        if not bounding_box:
            return None, False

        return ' '.join([
            str(max([bounding_box[0] - 10, 0])),
            str(max([bounding_box[1] - 10, 0])),
            str(bounding_box[2] - bounding_box[0] + 20),
            str(bounding_box[3] - bounding_box[1] + 20)
        ]), (bounding_box[2] - bounding_box[0]) > (bounding_box[3] - bounding_box[1])

    def get_and_format_results(self, page=None, paginate_by=None):
        """
        Generic function to overwrite to retrieve and format search results
        """
        pass

    def get_paginator(self, results, paginate_by):
        """
        Generic function to overwrite that must return a valid Paginator
        """
        return Paginator(results, paginate_by)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.no_extra_calculation_condition:
            return context

        try:
            page = int(self.request.GET.get('page', '1'))
        except ValueError:
            page = 1

        paginate_by = self.get_paginate_by(None)

        results, error = self.get_and_format_results(page=page, paginate_by=paginate_by)
        if error:
            context.update(error)
            return context

        # Pagination
        paginator = self.get_paginator(results, paginate_by)

        if page > paginator.num_pages:
            page = paginator.num_pages

        context['page_obj'] = paginator.page(page)
        context['is_paginated'] = paginator.num_pages > 1

        return context


class ESPaginator(Paginator):

    def __init__(self, *args, **kwargs):
        self._count = kwargs.pop('total')
        super(ESPaginator, self).__init__(*args, **kwargs)

    @cached_property
    def count(self):
        return self._count

    def page(self, number):
        number = self.validate_number(number)
        return Page(self.object_list, number, self)


class Search(BaseSearch):
    form_class = SearchForm
    template_name = 'core/search/search.html'
    es_total = 0

    @property
    def no_extra_calculation_condition(self):
        # No extra calculation if:
        # - the search feature is deactivated on the instance
        return settings.DISABLE_ELASTICSEARCH or super().no_extra_calculation_condition

    def convert_hit_to_template(self, hit):
        hit_source = hit['_source']
        highlight = hit.get('highlight', {})
        viewbox, larger = self.get_line_viewbox(hit_source['bounding_box'])

        return {
            'object': {
                'highlighted_content': highlight['raw_content'][0] if highlight.get('raw_content') else None,
                'line': {
                    'order': hit_source['line_number'] - 1,
                    'document_part': {
                        'id': hit_source['document_part_id'],
                        'title': hit_source['part_title'],
                        'document': {
                            'id': hit_source['document_id'],
                            'name': hit_source['document_name'],
                        }
                    }
                },
                'transcription': {
                    'id': hit_source['transcription_id'],
                    'name': hit_source['transcription_name'],
                },
            },
            'context_before': highlight['context_before'][0] if highlight.get('context_before') else None,
            'context_after': highlight['context_after'][0] if highlight.get('context_after') else None,
            'replacement_preview': None,
            'score': hit['_score'],
            'img_url': hit_source['image_url'],
            'img_w': hit_source['image_width'],
            'img_h': hit_source['image_height'],
            'viewbox': viewbox,
            'larger': larger
        }

    def get_and_format_results(self, page=None, paginate_by=None):
        try:
            es_results = self.form.search(page=page, paginate_by=paginate_by)
            self.es_total = int(es_results['hits']['total']['value'])
        except es_exceptions.ConnectionError as e:
            return [], {'es_error': str(e)}

        return [self.convert_hit_to_template(hit) for hit in es_results['hits']['hits']], None

    def get_paginator(self, results, paginate_by):
        return ESPaginator(results, paginate_by, total=self.es_total)

    def get_success_url(self):
        return reverse('search')


class FindAndReplace(BaseSearch):
    form_class = FindAndReplaceForm
    template_name = 'core/search/find_and_replace.html'
    paginate_by = 5

    def get_part_image_thumbnail(self, part_image):
        thumbnailer = get_thumbnailer(part_image)
        try:
            thumbnail = thumbnailer.get_thumbnail(
                settings.THUMBNAIL_ALIASES['']['large'], generate=False
            )
            assert thumbnail
        except Exception:
            thumbnail = part_image
            pass

        # Factors to scale line bboxes if necessary
        scale_factors = [
            thumbnail.width / part_image.width,
            thumbnail.height / part_image.height,
        ] * 2

        return thumbnail.url, thumbnail.width, thumbnail.height, scale_factors

    def get_line_bounding_box(self, line, scale_factors):
        line_box = line.get_box()
        if not line_box:
            return None

        return [
            ceil(value * factor)
            for value, factor in zip(line_box, scale_factors)
        ]

    def convert_lt_object_to_template(self, mode, find_terms, replace_term, lt_object, thumbnails):
        if lt_object.line.document_part_id not in thumbnails:
            try:
                thumbnail_url, thumbnail_width, thumbnail_height, scale_factors = self.get_part_image_thumbnail(lt_object.line.document_part.image)
            except FileNotFoundError:
                thumbnail_url, thumbnail_width, thumbnail_height = None, None, None
                scale_factors = [1, 1, 1, 1]

            thumbnails[lt_object.line.document_part_id] = {'url': thumbnail_url, 'width': thumbnail_width, 'height': thumbnail_height, 'scale_factors': scale_factors}

        bounding_box = self.get_line_bounding_box(lt_object.line, thumbnails[lt_object.line.document_part_id]['scale_factors'])
        viewbox, larger = self.get_line_viewbox(bounding_box)

        return {
            'object': lt_object,
            'context_before': None,
            'context_after': None,
            'replacement_preview': build_highlighted_replacement_psql(mode, find_terms, replace_term, lt_object.highlighted_content),
            'score': 100,
            'img_url': thumbnails[lt_object.line.document_part_id]['url'],
            'img_w': thumbnails[lt_object.line.document_part_id]['width'],
            'img_h': thumbnails[lt_object.line.document_part_id]['height'],
            'viewbox': viewbox,
            'larger': larger,
        }, thumbnails

    def get_mandatory_params(self):
        return self.form.cleaned_data.get('mode', WORD_BY_WORD_SEARCH_MODE), self.form.cleaned_data['query'], self.form.cleaned_data['replacement']

    def get_and_format_results(self, page=None, paginate_by=None):
        results = self.form.search()
        mode, find_terms, replace_term = self.get_mandatory_params()
        if mode == WORD_BY_WORD_SEARCH_MODE:
            find_terms = '|'.join(find_terms.split(' '))

        try:
            results = list(results)
        except DataError as e:
            self.form.add_error(None, f'Something went wrong while searching for results - {e}')
            return [], None

        thumbnails = {}
        template_results = []
        for lt_object in results:
            template_result, thumbnails = self.convert_lt_object_to_template(mode, find_terms, replace_term, lt_object, thumbnails)
            template_results.append(template_result)

        return template_results, None

    def get_filters(self):
        return {
            'mode': self.request.GET.get('mode'),
            'project': self.request.GET.get('project'),
            'document': self.request.GET.get('document'),
            'transcription': self.request.GET.get('transcription'),
            'part': self.request.GET.get('part'),
        }

    def post(self, request, *args, **kwargs):
        if 'apply_replace' not in self.request.POST:
            return super().post(request, *args, **kwargs)

        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)

        mode, find_terms, replace_term = self.get_mandatory_params()
        filters = self.get_filters()
        replace_line_transcriptions_text.delay(
            mode,
            find_terms,
            replace_term,
            project_pk=filters['project'],
            document_pk=filters['document'],
            transcription_pk=filters['transcription'],
            part_pk=filters['part'],
            user_pk=self.request.user.pk
        )
        return self.form_valid(form)

    def get_query_params(self):
        params = self.get_filters()
        query_params = '&'.join([f'{key}={value}' for key, value in params.items() if value is not None])
        return f'?{query_params}' if query_params else ''

    def get_success_url(self):
        return reverse('find-replace') + self.get_query_params()


class ProjectList(LoginRequiredMixin, PerPageMixin, ListView):
    model = Project
    paginate_by = 10

    def get_queryset(self):
        return (Project.objects
                .for_user_read(self.request.user)
                .annotate(documents_count=Count(
                    'documents',
                    filter=~Q(documents__workflow_state=Document.WORKFLOW_STATE_ARCHIVED),
                    distinct=True))
                .select_related('owner')
                .order_by('-updated_at'))


class CreateProject(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Project
    form_class = ProjectForm
    success_message = _("Project created successfully!")

    def get_success_url(self):
        return reverse('projects-list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        return response


class UpdateProject(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    success_message = _("Project updated successfully!")

    def get_object(self):
        obj = super().get_object()

        if not obj.owner == self.request.user:
            raise PermissionDenied

        return obj

    def get_success_url(self):
        return reverse('project-update', kwargs={'slug': self.object.slug})


class ProjectDashboard(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "core/project_dashboard.html"

    def get_queryset(self):
        return Project.objects.for_user_read(self.request.user)


class DocumentsList(LoginRequiredMixin, PerPageMixin, ListView):
    model = Document
    paginate_by = 10

    def get_queryset(self):
        self.project = (Project.objects
                        .get(slug=self.kwargs['slug']))
        try:
            Project.objects.for_user_read(self.request.user).get(pk=self.project.pk)
        except Project.DoesNotExist:
            raise PermissionDenied

        # Note: using subqueries for last edited part and first part (thumbnail)
        # to lower the amount of queries will make the sql time sky rocket!
        qs = (Document.objects
              .for_user(self.request.user)
              .filter(project=self.project)
              .prefetch_related('tags', 'parts', 'shared_with_groups', 'shared_with_users')
              )
        for tag in self.request.GET.getlist('tags'):
            qs = qs.filter(tags__name=tag)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        context['document_tags'] = list(self.project.document_tags.values())
        if self.project.owner == self.request.user:
            context['share_form'] = ProjectShareForm(instance=self.project,
                                                     request=self.request)

            context['can_create_document'] = True
        else:
            # can only create a new document if the whole project as been shared
            # not if some specific documents
            try:
                context['can_create_document'] = (Project.objects
                                                  .for_user_write(self.request.user)
                                                  .get(slug=self.kwargs['slug']))
            except Project.DoesNotExist:
                context['can_create_document'] = False

        context['filters'] = self.request.GET.getlist('tags')

        return context


class DocumentMixin():
    def get_success_url(self):
        return reverse('document-update', kwargs={'pk': self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_metadata_formset(self, *args, instance=None):
        if instance:
            qs = (Metadata.objects.filter(Q(public=True)
                                          | Q(documentmetadata__document=instance))
                  .distinct())
        else:
            qs = Metadata.objects.filter(public=True)
        return MetadataFormSet(*args, instance=instance, form_kwargs={'choices': qs})

    def get_object(self):
        obj = super().get_object()
        try:
            # we fetched the object already, now we check that the user has perms to edit it
            Document.objects.for_user(self.request.user).get(pk=obj.pk)
        except Document.DoesNotExist:
            raise PermissionDenied
        return obj


class CreateDocument(LoginRequiredMixin, SuccessMessageMixin, DocumentMixin, CreateView):
    model = Document
    form_class = DocumentForm

    success_message = _("Document created successfully!")

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        form.initial = {'project': self.project}
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['metadata_form'] = self.get_metadata_formset()
        return context

    def dispatch(self, request, *args, **kwargs):
        try:
            self.project = (Project.objects
                            .for_user_write(self.request.user)
                            .get(slug=self.request.resolver_match.kwargs['slug']))
        except Project.DoesNotExist:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        self.object = None
        metadata_form = self.get_metadata_formset(self.request.POST)
        if form.is_valid() and metadata_form.is_valid():
            return self.form_valid(form, metadata_form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form, metadata_form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        # form.save() has been called, we have an object
        metadata_form.instance = self.object
        metadata_form.save()
        return response


class UpdateDocument(LoginRequiredMixin, SuccessMessageMixin, DocumentMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    success_message = _("Document saved successfully!")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_publish'] = self.object.owner == self.request.user
        if 'metadata_form' not in kwargs:
            context['metadata_form'] = self.get_metadata_formset(instance=self.object)

        if self.object.owner == self.request.user:
            context['share_form'] = DocumentShareForm(instance=self.object,
                                                      request=self.request)
            context['migrate_form'] = MigrateDocumentForm(instance=self.object,
                                                          request=self.request)

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        form.initial = {'project': self.object.project}
        metadata_form = self.get_metadata_formset(self.request.POST, instance=self.object)
        if form.is_valid() and metadata_form.is_valid():
            return self.form_valid(form, metadata_form)
        else:
            return self.form_invalid(form, metadata_form)

    def form_invalid(self, form, metadata_form):
        return self.render_to_response(self.get_context_data(
            form=form, metadata_form=metadata_form))

    def form_valid(self, form, metadata_form):
        with transaction.atomic():
            response = super().form_valid(form)
            # at this point the document is saved
            metadata_form.save()
        return response


class DocumentOntology(LoginRequiredMixin, SuccessMessageMixin, DocumentMixin, UpdateView):
    model = Document
    form_class = DocumentOntologyForm
    template_name = "core/document_ontology.html"
    success_message = _("Ontology saved successfully!")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)

        if 'import_form' in request.POST:
            import_form = DocumentOntologyImportForm(request.POST, request.FILES, prefix='import_form')
            if not import_form.is_valid():
                context.update({'import_form': import_form, 'show_import_modal': True})
                return self.render_to_response(context)

            # Creating a TaskReport object to store warnings and errors that occur during deserialization
            report = TaskReport.objects.create(
                label=f'Ontology import from a JSON file in "{self.object}"',
                user=request.user,
                document=self.object,
            )
            report.start()

            updated_with_warnings = False
            try:
                # Parsing the provided JSON file
                json_ontology = json.loads(request.FILES.get('import_form-file').read())
                serializer = OntologyImportSerializer(self.object, data=json_ontology, report=report)

                # Checking its version is the supported one
                json_version = json_ontology.get('version')
                if json_version != serializer.VERSION:
                    raise Exception(f'JSON ontology file is in version {json_version}, currently supported version is {serializer.VERSION}')

                # Saving the data on the Document object
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

                updated_with_warnings = serializer.updated_with_warnings
            except Exception as e:
                report.error('[ERROR] ' + str(e))

                messages.error(self.request, _('Something went wrong during the ontology import...'), extra_tags=report.uri)
            else:
                report.end()

                if updated_with_warnings:
                    messages.warning(self.request, _('Ontology import finished with warnings.'), extra_tags=report.uri)
                else:
                    messages.success(self.request, _('Ontology import finished successfully!'), extra_tags=report.uri)

            return HttpResponseRedirect(self.get_success_url())

        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['import_form'] = DocumentOntologyImportForm(prefix='import_form')
        context['show_import_modal'] = False
        return context

    def get_success_url(self):
        return reverse('document-ontology', kwargs={'pk': self.object.pk})


class DocumentImages(LoginRequiredMixin, DocumentMixin, DetailView):
    model = Document
    template_name = "core/document_images.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_disk_storage_left'] = settings.DISABLE_QUOTAS or self.request.user.has_free_disk_storage()
        context['has_cpu_minutes_left'] = settings.DISABLE_QUOTAS or self.request.user.has_free_cpu_minutes()
        context['has_gpu_minutes_left'] = settings.DISABLE_QUOTAS or self.request.user.has_free_gpu_minutes()

        context['upload_form'] = UploadImageForm(document=self.object, user=self.request.user)

        # process forms
        context['segment_form'] = SegmentForm(self.object, self.request.user)
        context['transcribe_form'] = TranscribeForm(self.object, self.request.user)
        context['align_form'] = AlignForm(self.object, self.request.user)
        context['segtrain_form'] = SegTrainForm(self.object, self.request.user)
        context['rectrain_form'] = RecTrainForm(self.object, self.request.user)

        context['import_form'] = ImportForm(self.object, self.request.user)
        context['export_form'] = ExportForm(self.object, self.request.user)
        return context


class ShareDocument(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Document
    form_class = DocumentShareForm
    success_message = _("Document shared successfully!")
    http_method_names = ('post',)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        return reverse('document-update', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)


class DeleteDocumentUserShare(LoginRequiredMixin, View):
    http_method_names = ('post',)

    def post(self, *args, **kwargs):
        try:
            document = Document.objects.get(pk=self.request.POST['document'])
        except KeyError:
            raise HttpResponseBadRequest

        document.shared_with_users.remove(self.request.user)
        return HttpResponseRedirect(self.get_success_url(document))

    def get_success_url(self, document):
        if 'next' in self.request.GET:
            return self.request.GET.get('next')
        else:
            return reverse('documents-list', kwargs={'slug': document.project.slug})


class ShareProject(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Project
    form_class = ProjectShareForm
    success_message = _("Project shared successfully!")
    http_method_names = ('post',)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        return reverse('documents-list', kwargs={'slug': self.object.slug})

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)


class DeleteProjectUserShare(LoginRequiredMixin, View):
    http_method_names = ('post',)

    def post(self, *args, **kwargs):
        try:
            project = Project.objects.get(pk=self.request.POST['project'])
        except KeyError:
            raise HttpResponseBadRequest

        project.shared_with_users.remove(self.request.user)
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        if 'next' in self.request.GET:
            return self.request.GET.get('next')
        else:
            return reverse('projects-list')


class PublishDocument(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Document
    fields = ['workflow_state']
    http_method_names = ('post',)

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)

    def get_success_message(self, form_data):
        if self.object.is_archived:
            return _("Document archived successfully!")
        else:
            return _("Document published successfully!")

    def get_success_url(self):
        if self.object.is_archived:
            return reverse('documents-list', kwargs={'slug': self.object.project.slug})
        else:
            return reverse('document-update', kwargs={'pk': self.object.pk})


class DocumentPartsProcessAjax(LoginRequiredMixin, View):
    # TODO: move to api
    http_method_names = ('post',)

    def get_document(self):
        return Document.objects.for_user(self.request.user).get(pk=self.kwargs['pk'])

    def post(self, request, *args, **kwargs):
        try:
            document = self.get_document()
        except Document.DoesNotExist:
            return HttpResponse(json.dumps({'status': 'Not Found'}),
                                status=404, content_type="application/json")

        task = self.request.POST.get('task')
        if task == 'segment':
            form_class = SegmentForm
        elif task == 'transcribe':
            form_class = TranscribeForm
        elif task == 'align':
            form_class = AlignForm
        elif task == 'segtrain':
            form_class = SegTrainForm
        elif task == 'train':
            form_class = RecTrainForm

        form = form_class(document,
                          self.request.user,
                          self.request.POST,
                          self.request.FILES)

        if form.is_valid():
            try:
                form.process()
            except AlreadyProcessingException:
                return HttpResponse(json.dumps({'status': 'error', 'error': 'Already processing.'}),
                                    content_type="application/json", status=400)
            return HttpResponse(json.dumps({'status': 'ok'}), content_type="application/json")
        else:
            return HttpResponse(json.dumps({'status': 'error', 'error': json.dumps(form.errors)}),
                                content_type="application/json", status=400)


class DocumentDashboard(LoginRequiredMixin, DetailView):
    model = Document
    template_name = "core/document_dashboard.html"

    def get_queryset(self):
        return Document.objects.for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data.update({
            "document_id": self.get_object().pk
        })
        return context_data


class EditPart(LoginRequiredMixin, DetailView):
    model = DocumentPart
    pk_url_kwarg = 'part_pk'
    template_name = "core/document_part_edit.html"
    http_method_names = ('get',)

    def get_object(self):
        obj = super().get_object()
        try:
            # we fetched the object already, now we check that the user has perms to edit it
            Document.objects.for_user(self.request.user).get(pk=obj.document.pk)
        except Document.DoesNotExist:
            raise PermissionDenied
        return obj

    def get_queryset(self):
        return DocumentPart.objects.filter(
            document=self.kwargs.get('pk')).select_related('document')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Note: a bit confusing but this view uses the same base template than UpdateDocument
        # so we need context['object'] = document
        context['object'] = self.object.document
        context['document'] = self.object.document
        context['part'] = self.object
        return context

    def dispatch(self, *args, **kwargs):
        if 'part_pk' not in self.kwargs:
            try:
                first = self.get_queryset()[0]
                return HttpResponseRedirect(reverse('document-part-edit',
                                                    kwargs={'pk': first.document.pk,
                                                            'part_pk': first.pk}))
            except IndexError:
                raise Http404
        else:
            return super().dispatch(*args, **kwargs)


class DocumentModels(LoginRequiredMixin, PerPageMixin, ListView):
    model = OcrModel
    template_name = "core/models_list/document_models.html"
    http_method_names = ('get',)
    paginate_by = 20

    def get_queryset(self):
        try:
            self.document = Document.objects.for_user(self.request.user).get(pk=self.kwargs.get('document_pk'))
        except Document.DoesNotExist:
            raise PermissionDenied
        return self.document.ocr_models.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['document'] = self.document
        context['object'] = self.document  # legacy
        return context


class UserModels(LoginRequiredMixin, PerPageMixin, ListView):
    model = OcrModel
    template_name = "core/models_list/main.html"
    http_method_names = ('get',)
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        models = OcrModel.objects.exclude(file="").filter(
            Q(public=True)
            | Q(owner=user)
            | Q(ocr_model_rights__user=user)
            | Q(ocr_model_rights__group__user=user)
        ).distinct()

        script_filter = self.request.GET.get('script_filter', '')
        if script_filter:
            models = models.filter(script__name=script_filter)

        return models

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['script_filter'] = self.request.GET.get('script_filter', '')
        return context


class ModelUpload(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = OcrModel
    form_class = ModelUploadForm
    success_message = _("Model uploaded successfully!")

    def get_success_url(self):
        return reverse('user-models')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_disk_storage_left'] = settings.DISABLE_QUOTAS or self.request.user.has_free_disk_storage()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs


class ModelUnbind(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = OcrModelDocument

    def get_object(self):
        try:
            return OcrModelDocument.objects.filter(
                document__owner=self.request.user,
                document__pk=self.kwargs['docPk'],
                ocr_model__pk=self.kwargs['pk'])
        except OcrModelDocument.DoesNotExist:
            raise Http404

    def get_success_url(self):
        if 'next' in self.request.GET:
            return self.request.GET.get('next')
        else:
            return reverse('user-models')


class ModelDelete(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = OcrModel
    success_message = _("Model deleted successfully!")

    def get_queryset(self):
        return OcrModel.objects.filter(owner=self.request.user)

    def get_success_url(self):
        if 'next' in self.request.GET:
            return self.request.GET.get('next')
        else:
            return reverse('user-models')


class ModelCancelTraining(LoginRequiredMixin, SuccessMessageMixin, DetailView):
    model = OcrModel
    http_method_names = ('post',)

    def get_success_url(self):
        if 'next' in self.request.GET:
            return self.request.GET.get('next')
        else:
            return reverse('user-models')

    def post(self, request, *args, **kwargs):
        model = self.get_object()
        try:
            model.cancel_training(username=request.user.username)
        except Exception as e:
            logger.exception(e)
            return HttpResponse({'status': 'failed'}, status=400,
                                content_type="application/json")
        else:
            return HttpResponseRedirect(self.get_success_url())


class ModelRights(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = OcrModelRight
    template_name = "core/models_list/rights/main.html"
    success_message = _("Right added successfully!")
    form_class = ModelRightsForm

    def get_context_data(self, **kwargs):
        model = get_object_or_404(OcrModel, pk=self.kwargs['pk'])

        if self.request.user != model.owner or model.public:
            raise PermissionDenied

        kwargs['object_list'] = model.ocr_model_rights.all()
        kwargs['model_name'] = model.name

        return super().get_context_data(**kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'ocr_model_id': self.kwargs['pk']})
        return kwargs

    def form_valid(self, form):
        form.instance.ocr_model = OcrModel.objects.get(pk=self.kwargs['pk'])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('model-rights', kwargs={'pk': self.kwargs['pk']})


class ModelRightDelete(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = OcrModelRight
    template_name = 'core/models_list/rights/delete.html'
    success_message = _("Right deleted successfully!")

    def get_context_data(self, **kwargs):
        model = get_object_or_404(OcrModel, pk=self.kwargs['modelPk'])

        if self.request.user != model.owner or model.public:
            raise PermissionDenied

        return super().get_context_data(**kwargs)

    def get_success_url(self):
        return reverse('model-rights', kwargs={'pk': self.kwargs['modelPk']})


class DocumentsTasksList(LoginRequiredMixin, TemplateView):
    template_name = 'core/documents_tasks_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['task_states'] = {state: label for state, label in TaskReport.WORKFLOW_STATE_CHOICES}
        context['users'] = {
            user.id: user.username for user in User.objects.all()
        } if self.request.user and self.request.user.is_staff else {}

        return context


class MigrateDocument(ShareDocument):
    form_class = MigrateDocumentForm
    success_message = _("Document was successfully migrated to the selected project!")
