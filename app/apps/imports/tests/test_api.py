import os.path
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse

from core.models import (
    Block,
    BlockType,
    Line,
    LineTranscription,
    LineType,
    Transcription,
)
from core.tests.factory import CoreFactoryTestCase
from imports.models import DocumentImport
from imports.parsers import AltoParser, IIIFManifestParser
from reporting.models import TaskReport

# DO NOT REMOVE THIS IMPORT, it will break a lot of tests
# It is used to trigger Celery signals when running tests
from reporting.tasks import end_task_reporting  # noqa F401
from reporting.tasks import start_task_reporting  # noqa F401


class XmlImportTestCase(CoreFactoryTestCase):
    def setUp(self):
        super().setUp()
        self.document = self.factory.make_document()
        self.part1 = self.factory.make_part(name='part 1',
                                            document=self.document,
                                            original_filename='test1.png')
        self.part2 = self.factory.make_part(name='part 2',
                                            document=self.document,
                                            original_filename='test2.png')
        self.part3 = self.factory.make_part(name='part 3',
                                            document=self.document,
                                            original_filename='test3.png')
        self.client.force_login(self.document.owner)

    def test_alto_single_no_match(self):
        self.part1.original_filename = 'temp'
        self.part1.save()

        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_single.alto'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(25):
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                # # Note: the ParseError is raised by the processing of the import,
                # not the validation!
                # # the error is sent via websocket so no need to catch it here
                self.assertEqual(response.status_code, 200)

        # failed, didn't create anythng
        self.assertEqual(self.part1.blocks.count(), 0)
        self.assertEqual(self.part1.lines.count(), 0)

        # import was created since the form validated
        imp = DocumentImport.objects.first()
        self.assertTrue(imp.report.messages.startswith('No match found for file test_single'))

    def test_alto_invalid_xml(self):
        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_invalid_alto.xml'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(6):
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                self.assertEqual(response.status_code, 400)

    def test_alto_single_bbox(self):
        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_single.alto'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(61):
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b'{"status":"ok"}')

        self.assertEqual(DocumentImport.objects.count(), 1)
        imp = DocumentImport.objects.first()
        self.assertEqual(imp.error_message, None)
        self.assertEqual(imp.workflow_state, DocumentImport.WORKFLOW_STATE_DONE)
        self.assertEqual(self.part1.blocks.count(), 1)
        self.assertEqual(self.part1.blocks.first().box, [[0, 0], [850, 0], [850, 1083], [0, 1083]])
        self.assertEqual(self.part1.lines.count(), 3)
        self.assertEqual(self.part1.lines.first().box, [160, 771, 220, 771])
        self.assertEqual(self.part1.lines.first().transcriptions.first().content, 'This is a test')
        self.assertEqual(self.part2.blocks.count(), 0)
        self.assertEqual(self.part2.lines.count(), 0)

    def test_alto_single_baseline(self):
        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_single_baselines.alto'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(45):
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.content, b'{"status":"ok"}')

        self.assertEqual(DocumentImport.objects.count(), 1)
        imp = DocumentImport.objects.first()
        self.assertEqual(imp.error_message, None)
        self.assertEqual(imp.workflow_state, DocumentImport.WORKFLOW_STATE_DONE)
        self.assertEqual(self.part1.blocks.count(), 1)
        self.assertEqual(self.part1.blocks.first().box, [[0, 0], [850, 0], [850, 1083], [0, 1083]])
        self.assertEqual(self.part1.lines.count(), 1)
        line = self.part1.lines.first()
        self.assertEqual(line.baseline, [[160, 771], [170, 772], [190, 782], [220, 772]])
        self.assertEqual(line.mask, [[158, 770], [225, 770], [225, 750], [158, 750]])
        self.assertEqual(line.transcriptions.first().content, 'This is a test')

    def test_alto_multi(self):
        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test.zip'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(80):
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                self.assertEqual(response.content, b'{"status":"ok"}', response.content)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(DocumentImport.objects.count(), 1)
        self.assertEqual(DocumentImport.objects.first().workflow_state,
                         DocumentImport.WORKFLOW_STATE_DONE)

        self.assertEqual(self.part1.blocks.count(), 1)
        self.assertEqual(self.part1.lines.count(), 3)
        self.assertEqual(self.part2.blocks.count(), 1)
        self.assertEqual(self.part2.lines.count(), 1)

    def test_alto_types(self):
        bt = BlockType.objects.create(name="test_block_type")
        lt = LineType.objects.create(name="test_line_type")
        self.document.valid_block_types.add(bt)
        self.document.valid_line_types.add(lt)
        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_composedblock.alto'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(87):
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                self.assertEqual(response.content, b'{"status":"ok"}', response.content)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(DocumentImport.objects.count(), 1)
        self.assertEqual(DocumentImport.objects.first().workflow_state,
                         DocumentImport.WORKFLOW_STATE_DONE)
        self.assertEqual(self.part1.blocks.count(), 3)

        # one of each created automatically
        self.assertEqual(self.document.valid_block_types.count(), 2)
        self.assertEqual(self.document.valid_line_types.count(), 2)

        self.assertEqual(self.part1.blocks.all()[0].typology, None)
        self.assertEqual(self.part1.blocks.all()[1].typology.name, 'test_block_type')
        self.assertEqual(self.part1.blocks.all()[2].typology.name, 'new_block_type')
        self.assertEqual(self.part1.lines.all()[0].typology, None)
        self.assertEqual(self.part1.lines.all()[1].typology.name, 'test_line_type')
        self.assertEqual(self.part1.lines.all()[2].typology.name, 'new_line_type')
        self.assertEqual(self.part1.lines.count(), 3)

    def test_resume(self):
        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test.zip'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with transaction.atomic():
                imp = DocumentImport.objects.create(
                    document=self.document,
                    started_by=self.document.owner,
                    import_file=SimpleUploadedFile(filename, fh.read()),
                    workflow_state=DocumentImport.WORKFLOW_STATE_ERROR,
                    processed=0)

        response = self.client.post(uri, {'resume_import': True})
        self.assertEqual(response.status_code, 200)
        imp.refresh_from_db()
        self.assertEqual(imp.workflow_state, imp.WORKFLOW_STATE_DONE)

    def test_name(self):
        trans = Transcription.objects.create(name=AltoParser.DEFAULT_NAME, document=self.document)
        b = Block.objects.create(document_part=self.part1, external_id="textblock_0",
                                 box=[[0, 0], [100, 100]])
        line = Line.objects.create(document_part=self.part1, block=b, external_id="line_0",
                                   baseline=((5, 5), (5, 10)),
                                   mask=((0, 0), (0, 10), (10, 0), (10, 10)))
        LineTranscription.objects.create(transcription=trans, line=line)

        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_single.alto'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            response = self.client.post(uri, {
                'name': AltoParser.DEFAULT_NAME,
                'upload_file': SimpleUploadedFile(filename, fh.read())
            })
            self.assertEqual(response.content, b'{"status":"ok"}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.document.transcriptions.count(), 2)  # manual and 'test import'
            self.assertEqual(self.part1.lines.count(), 3)

            fh.seek(0)
            response = self.client.post(uri, {
                'upload_file': SimpleUploadedFile(filename, fh.read())
            })
            self.assertEqual(response.content, b'{"status":"ok"}')
            self.assertEqual(response.status_code, 200)
            # we created a new transcription
            self.assertEqual(self.document.transcriptions.count(), 2)
            # still the same number of lines
            self.assertEqual(self.part1.lines.count(), 3)

    def test_override(self):
        trans = Transcription.objects.create(name=AltoParser.DEFAULT_NAME, document=self.document)
        b = Block.objects.create(document_part=self.part1, external_id="textblock_0",
                                 box=[[0, 0], [100, 100]])
        line = Line.objects.create(document_part=self.part1, block=b, external_id="line_0",
                                   baseline=((5, 5), (5, 10)),
                                   mask=((0, 0), (0, 10), (10, 0), (10, 10)))
        lt = LineTranscription.objects.create(transcription=trans, line=line, content="test history")

        # historic line without external_id
        b2 = Block.objects.create(document_part=self.part1, box=[[0, 0], [100, 100]])
        l2 = Line.objects.create(document_part=self.part1, block=b2, baseline=((10, 10), (50, 20)))
        LineTranscription.objects.create(transcription=trans, line=l2, content="test dummy")

        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_single.alto'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            response = self.client.post(uri, {
                'override': False,
                'upload_file': SimpleUploadedFile(filename, fh.read())
            })
            self.assertEqual(response.content, b'{"status":"ok"}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.part1.lines.count(), 4)  # 3 from import + 1 existing
            lt.refresh_from_db()

            self.assertEqual(len(lt.history), 1)
            self.assertEqual(lt.history[0].content, 'test history')

            fh.seek(0)
            response = self.client.post(uri, {
                'override': True,
                'upload_file': SimpleUploadedFile(filename, fh.read())
            })
            self.assertEqual(response.content, b'{"status":"ok"}')
            self.assertEqual(response.status_code, 200)
            # this time we erased the existing line
            self.assertEqual(self.part1.lines.count(), 3)

    def test_pagexml_single_no_match(self):
        self.part3.original_filename = 'temp'
        self.part3.save()

        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'pagexml_test.xml'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(25):
                response = self.client.post(uri, {'upload_file': SimpleUploadedFile(filename,
                                                                                    fh.read())})
                # Note: the ParseError is raised by the processing of the import,
                # not the validation!
                # the error is sent via websocket so no need to catch it here
                self.assertEqual(response.status_code, 200)

        # failed, didn't create anythng
        self.assertEqual(self.part3.blocks.count(), 0)
        self.assertEqual(self.part3.lines.count(), 0)
        # import was created since the form validated
        imp = DocumentImport.objects.first()
        self.assertTrue(imp.report.messages.startswith('No match found'))
        self.part3.original_filename = 'test3.png'
        self.part3.save()

    def test_parse_pagexml_single_file(self):
        trans = Transcription.objects.create(name="test import", document=self.document)
        block = Block.objects.create(document_part=self.part3, external_id="r2",
                                     box=[[0, 0], [100, 100]])
        line = Line.objects.create(document_part=self.part3, block=block, external_id="r2l1",
                                   baseline=((5, 5), (5, 10)),
                                   mask=((0, 0), (0, 10), (10, 0), (10, 10)))
        LineTranscription.objects.create(transcription=trans, line=line)

        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'pagexml_test.xml'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            response = self.client.post(uri, {
                'upload_file': SimpleUploadedFile(filename, fh.read())
            })
        self.assertEqual(response.content, b'{"status":"ok"}', response.content)
        self.assertEqual(response.status_code, 200)
        # we created a new transcription
        self.assertEqual(self.document.transcriptions.count(), 3)
        self.assertEqual(self.part3.lines.count(), 21)
        self.assertEqual(self.part3.blocks.count(), 2)

    def test_parse_transkribus_pagexml(self):

        trans = Transcription.objects.create(name="test import", document=self.document)
        block = Block.objects.create(document_part=self.part3, external_id="r2",
                                     box=[[0, 0], [100, 100]])
        line = Line.objects.create(document_part=self.part3,
                                   block=block,
                                   external_id="r2l1",
                                   baseline=((5, 5), (5, 10)),
                                   mask=((0, 0), (0, 10), (10, 0), (10, 10)))
        LineTranscription.objects.create(transcription=trans, line=line)

        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'transkribus_test.xml'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            response = self.client.post(uri, {
                'upload_file': SimpleUploadedFile(filename, fh.read())
            })
        self.assertEqual(response.content, b'{"status":"ok"}')
        self.assertEqual(response.status_code, 200)
        # we created a new transcription

        block.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(block.box, [[113, -29], [113, 1021], [697, 1021], [697, 29]])
        self.assertEqual(line.mask, [[150.3, 64], [0, 60], [425, 81], [460, 60], [616, 64], [621, 5]])
        self.assertEqual(line.baseline, [[155.0, 55.0], [180.0, 55.0], [0, 55.0], [231.3, 55.0]])

    def test_parse_pagexml_zipped_file(self):
        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_pagexml.zip'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(417):  # there's a lot of lines in there
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                self.assertEqual(response.content, b'{"status":"ok"}', response.content)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(DocumentImport.objects.count(), 1)
        self.assertEqual(DocumentImport.objects.first().workflow_state,
                         DocumentImport.WORKFLOW_STATE_DONE)
        self.assertEqual(self.part1.blocks.count(), 0)
        self.assertEqual(self.part1.lines.count(), 18)
        self.assertEqual(self.part2.blocks.count(), 0)
        self.assertEqual(self.part2.lines.count(), 57)
        self.assertEqual(self.part3.blocks.count(), 0)
        self.assertEqual(self.part3.lines.count(), 19)

    def test_pagexml_types(self):
        non_word_block_type = "test-non-word-block-type"
        word_block_type = 'heading'
        non_word_line_type = 'test-non-word_line_type'
        bt_head = BlockType.objects.create(name=word_block_type)
        bt_non_word = BlockType.objects.create(name=non_word_block_type)
        lt_non_word = LineType.objects.create(name=non_word_line_type)
        self.document.valid_block_types.add(bt_head)
        self.document.valid_block_types.add(bt_non_word)
        self.document.valid_line_types.add(lt_non_word)

        uri = reverse('api:document-imports', kwargs={'pk': self.document.pk})
        filename = 'test_pagexml_types.xml'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            with self.assertNumQueries(93):
                response = self.client.post(uri, {
                    'upload_file': SimpleUploadedFile(filename, fh.read())
                })
                self.assertEqual(response.content, b'{"status":"ok"}', response.content)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(DocumentImport.objects.count(), 1)
        self.assertEqual(DocumentImport.objects.first().workflow_state,
                         DocumentImport.WORKFLOW_STATE_DONE)
        self.assertEqual(self.part1.blocks.count(), 4)

        # 1 of each created automatically
        self.assertEqual(self.document.valid_block_types.count(), 3)
        self.assertEqual(self.document.valid_line_types.count(), 2)

        self.assertEqual(self.part1.blocks.all()[0].typology, None)
        self.assertEqual(self.part1.blocks.all()[1].typology.name, non_word_block_type)
        self.assertEqual(self.part1.blocks.all()[2].typology.name, word_block_type)
        self.assertEqual(self.part1.blocks.all()[3].typology.name, 'new_block_type')  # created
        self.assertEqual(self.part1.lines.all()[0].typology, None)
        self.assertEqual(self.part1.lines.all()[1].typology.name, non_word_line_type)
        self.assertEqual(self.part1.lines.all()[2].typology.name, 'new_line_type')  # created
        self.assertEqual(self.part1.lines.count(), 3)

    def test_iiif(self):
        filename = 'iiif.json'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:

            imp = DocumentImport(
                document=self.document,
                name='test',
                started_by=self.document.owner,
                report=TaskReport.objects.create(
                    user=self.document.owner,
                    label="Test import",
                    document=self.document,
                    method="imports.tasks.document_import",
                )
            )
            imp.import_file.save(
                'iiif_manifest.json',
                ContentFile(fh.read()))

            # we don't go through the form but we want to test json validation
            fh.seek(0)
            IIIFManifestParser(self.document, fh, imp.report).validate()

            imp.save()

        # mock images grabbing
        filename = 'test.png'
        mock_path = os.path.join(os.path.dirname(__file__), 'mocks', filename)
        with open(mock_path, 'rb') as fh:
            # mock the image grabbing
            mock_resp = mock.Mock(content=fh.read(), status_code=200)
            with mock.patch('requests.get', return_value=mock_resp):
                for part in imp.process():  # exhaust the generator
                    pass

        self.assertEqual(imp.workflow_state, imp.WORKFLOW_STATE_DONE)
        self.assertEqual(imp.processed, 5)

        # +2 from factory # change 7 by 8 i addedpart 3 manually
        self.assertEqual(self.document.parts.count(), 8)

    def test_cancel(self):
        # Note: not actually testing celery's revoke
        DocumentImport.objects.create(
            document=self.document,
            import_file=ContentFile('', name='doesntmatter.xml'),
            workflow_state=DocumentImport.WORKFLOW_STATE_STARTED,
            started_by=self.document.owner,
            processed=0)
        uri = reverse('api:document-cancel-import', kwargs={'pk': self.document.pk})
        response = self.client.post(uri)
        self.assertEqual(response.status_code, 200)

        # already canceled
        response = self.client.post(uri)
        self.assertEqual(response.status_code, 400)


class ImportEndpointTestCase(CoreFactoryTestCase):
    def setUp(self):
        super().setUp()
        self.doc = self.factory.make_document()
        self.user = self.doc.owner

    def test_iiif(self):
        self.client.force_login(self.user)
        mock_iiif = os.path.join(os.path.dirname(__file__), 'mocks', 'iiif.json')

        # Note image grabbing get mocked with the same .json file but it doesn't matter
        with open(mock_iiif, 'rb') as fh:
            mock_resp = mock.Mock(content=fh.read(), status_code=200)
            with mock.patch('requests.get', return_value=mock_resp):
                with mock.patch('imports.parsers.ParserDocument.post_process_image'):
                    uri = reverse('api:import-list', kwargs={'document_pk': self.doc.pk})
                    resp = self.client.post(uri, {
                        'mode': 'iiif',
                        'iiif_uri': 'http://some.com/url/'})
                    self.assertEqual(resp.status_code, 201, resp.content)
                    self.assertEqual(DocumentImport.objects.count(), 1)
                    self.assertEqual(self.doc.parts.count(), 5)

    def test_mets_local(self):
        self.client.force_login(self.user)
        mock_mets = os.path.join(os.path.dirname(__file__), 'samples', 'simple_archive.zip')
        with open(mock_mets, 'rb') as fh:
            uri = reverse('api:import-list', kwargs={'document_pk': self.doc.pk})
            resp = self.client.post(uri, {
                'mode': 'mets',
                'mets_type': 'local',
                'upload_file': SimpleUploadedFile('arch.zip', fh.read())})

            self.assertEqual(resp.status_code, 201, resp.content)

            self.assertEqual(DocumentImport.objects.count(), 1)

            self.assertEqual(self.doc.metadatas.count(), 4)
            self.assertEqual(self.doc.parts.count(), 4)

    def test_mets_uri(self):
        self.client.force_login(self.user)

        mock_mets = os.path.join(os.path.dirname(__file__), 'samples', 'mets_with_images.xml')
        mock_xml = os.path.join(os.path.dirname(__file__), 'mocks', 'pagexml_test.xml')
        mock_image = os.path.join(os.path.dirname(__file__), 'mocks', 'test.png')

        with open(mock_mets, 'rb') as fh:
            mock_mets_resp = mock.Mock(content=fh.read(),
                                       status_code=200,
                                       headers={'content-type': 'text/xml'})
        with open(mock_xml, 'rb') as fh:
            mock_xml_resp = mock.Mock(content=fh.read(),
                                      status_code=200,
                                      headers={'content-type': 'text/xml'})
        with open(mock_image, 'rb') as fh:
            mock_img_resp = mock.Mock(content=fh.read(),
                                      status_code=200,
                                      headers={'content-type': 'image/png'})

        with mock.patch('requests.get', side_effect=[mock_mets_resp,
                                                     mock_img_resp,
                                                     mock_xml_resp,
                                                     mock_img_resp,
                                                     mock_xml_resp]):
            uri = reverse('api:import-list', kwargs={'document_pk': self.doc.pk})
            resp = self.client.post(uri, {
                'mode': 'mets',
                'mets_type': 'url',
                'mets_uri': 'http://some.com/url/'})

            self.assertEqual(resp.status_code, 201, resp.content)

            self.assertEqual(DocumentImport.objects.count(), 1)
            self.assertEqual(self.doc.parts.count(), 2)

    def test_xml(self):
        part1 = self.factory.make_part(name='part 1',
                                       document=self.doc,
                                       original_filename='test1.png')

        self.client.force_login(self.user)
        mock_xml = os.path.join(os.path.dirname(__file__), 'mocks', 'test.zip')
        with open(mock_xml, 'rb') as fh:
            uri = reverse('api:import-list', kwargs={'document_pk': self.doc.pk})
            resp = self.client.post(uri, {
                'mode': 'xml',
                'upload_file': SimpleUploadedFile('test.zip', fh.read())
            })
            self.assertEqual(resp.status_code, 201, resp.content)
            self.assertEqual(DocumentImport.objects.count(), 1)
            self.assertEqual(part1.blocks.count(), 1)
            self.assertEqual(part1.blocks.first().box, [[0, 0], [850, 0], [850, 1083], [0, 1083]])
            self.assertEqual(part1.lines.count(), 3)

    def test_pdf(self):
        pass


class DocumentExportTestCase(CoreFactoryTestCase):
    def setUp(self):
        super().setUp()

        self.trans = self.factory.make_transcription()
        self.user = self.trans.document.owner  # shortcut
        self.parts = []
        for i in range(1, 3):
            part = self.factory.make_part(name='part %d' % i,
                                          document=self.trans.document)
            self.parts.append(part)
            for j in range(1, 4):
                line = Line.objects.create(document_part=part,
                                           baseline=((5, 5), (5, 10)),
                                           mask=((0, 0), (0, 10), (10, 0), (10, 10)))
                LineTranscription.objects.create(
                    line=line,
                    transcription=self.trans,
                    content='line %d:%d' % (i, j))

        self.region_types_choices = list(
            self.trans.document.valid_block_types.values_list('id', flat=True)
        ) + ['Undefined', 'Orphan']

    def test_simple(self):
        self.client.force_login(self.user)
        with self.assertNumQueries(22):
            response = self.client.post(reverse('api:document-export',
                                                kwargs={'pk': self.trans.document.pk}),
                                        {'transcription': self.trans.pk,
                                         'file_format': 'text',
                                         'parts': [str(p.pk) for p in self.parts],
                                         'region_types': self.region_types_choices})
            self.assertEqual(response.status_code, 200)

        # self.assertEqual(''.join([c.decode() for c in response.streaming_content]),
        #                  "line 1:1\nline 1:2\nline 1:3\nline 2:1\nline 2:2\nline 2:3\n")

    def test_alto(self):
        self.client.force_login(self.user)
        with self.assertNumQueries(32):
            response = self.client.post(reverse('api:document-export',
                                                kwargs={'pk': self.trans.document.pk}),
                                        {'transcription': self.trans.pk,
                                         'file_format': 'alto',
                                         'parts': [str(p.pk) for p in self.parts],
                                         'region_types': self.region_types_choices})
            self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.content, '')

    def test_alto_qs_scaling(self):
        for i in range(4, 20):
            part = self.factory.make_part(name='part %d' % i,
                                          document=self.trans.document)
            block = Block.objects.create(document_part=part, box=(0, 0, 1, 1))
            for j in range(1, 4):
                line = Line.objects.create(document_part=part,
                                           block=block,
                                           baseline=((5, 5), (5, 10)),
                                           mask=((0, 0), (0, 10), (10, 0), (10, 10)))
                LineTranscription.objects.create(
                    line=line,
                    transcription=self.trans,
                    content='line %d:%d' % (i, j))
        self.client.force_login(self.user)
        with self.assertNumQueries(32):
            response = self.client.post(reverse('api:document-export',
                                                kwargs={'pk': self.trans.document.pk}),
                                        {'transcription': self.trans.pk,
                                         'file_format': 'alto',
                                         'parts': [str(p.pk) for p in self.parts],
                                         'region_types': self.region_types_choices})
            self.assertEqual(response.status_code, 200)

    def test_invalid(self):
        self.client.force_login(self.user)
        # invalid file format
        response = self.client.post(reverse('api:document-export',
                                            kwargs={'pk': self.trans.document.pk}),
                                    {'transcription': self.trans.pk,
                                     'file_format': 'pouet',
                                     'parts': [str(p.pk) for p in self.parts],
                                     'region_types': self.region_types_choices})
        self.assertEqual(response.status_code, 400)
