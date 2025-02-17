import axios from "axios";
import {
    createDocumentMetadata,
    deleteDocument,
    deleteDocumentMetadata,
    editDocument,
    retrieveDocument,
    retrieveDocumentMetadata,
    retrieveDocumentModels,
    retrieveDocumentParts,
    retrieveDocumentStats,
    retrieveDocumentTasks,
    retrieveTextualWitnesses,
    retrieveTranscriptionStats,
    shareDocument,
    updateDocumentMetadata,
} from "../../../src/api";
import { tagColorToVariant } from "../util/color";
import { getMetadataCRUD } from "../util/metadata";
import forms from "../util/initialFormState";
import { throttle } from "../util/throttle";

// initial state
const state = () => ({
    deleteModalOpen: false,
    // list of all possible document tags from project
    documentTags: [],
    editModalOpen: false,
    id: null,
    lastModified: "",
    linePosition: null,
    loading: {
        document: true,
        models: true,
        parts: true,
        tasks: true,
        user: true,
    },
    mainScript: "",
    menuOpen: false,
    /**
     * metadata: [{
     *     pk: Number,
     *     key: {
     *         name: String,
     *     },
     *     value: String,
     * }]
     */
    metadata: [],
    /**
     * models: [{
     *     pk: Number,
     *     name: String,
     *     file: String,
     *     file_size: Number,
     *     job: String,
     *     rights: String,
     *     training: Boolean,
     *     accuracy_percent?: Number,
     *     model?: String,
     *     parent?: String,
     * }]
     */
    models: [],
    name: "",
    /**
     * parts: [{
     *     pk: Number,
     *     thumbnail: String,
     *     order: Number,
     *     title: String,
     * }]
     */
    parts: [],
    partsCount: null,
    projectId: null,
    projectName: "",
    projectSlug: "",
    readDirection: "",
    /**
     * regionTypes: [{
     *     pk: Number,
     *     name: String,
     * }]
     */
    regionTypes: [],
    /**
     * sharedWithGroups: [{
     *     pk: Number,
     *     name: String,
     * }]
     */
    sharedWithGroups: [],
    /**
     * sharedWithUsers: [{
     *     pk: Number,
     *     first_name?: String,
     *     last_name?: String,
     *     username: String,
     * }]
     */
    sharedWithUsers: [],
    shareModalOpen: false,
    /**
     * tags: [{
     *     name: String,
     *     pk: Number,
     *     variant: Number,
     * }]
     */
    tags: [],
    /**
     * tasks: [{
     *     pk: Number,
     *     document: Number,
     *     workflow_state: Number,
     *     label: String,
     *     messages?: String,
     *     queued_at: String,
     *     started_at: String
     *     done_at: String,
     *     method: String,
     *     user: Number,
     * }]
     */
    tasks: [],
    /**
     * textualWitnesses: [{
     *     name: String,
     *     pk: Number,
     *     owner: String,
     *     file: String,
     * }]
     */
    textualWitnesses: [],
    /**
     * transcriptions: [{
     *     name: String,
     *     pk: Number,
     *     archived: Boolean,
     *     avg_confidence?: Number,
     * }]
     */
    transcriptions: [],
    types: [],
});

const getters = {};

const actions = {
    /**
     * Change the selected transcription and fetch its ontology/characters.
     */
    async changeSelectedTranscription(
        { commit, dispatch, state },
        transcriptionId,
    ) {
        commit("transcription/setSelectedTranscription", transcriptionId, {
            root: true,
        });
        // update counts
        const transcription = state.transcriptions.find(
            (t) => t.pk === transcriptionId,
        );
        if (transcription) {
            const { lines_count } = transcription;
            commit("transcription/setLineCount", lines_count, { root: true });
        }
        // kickoff fetch
        try {
            commit("characters/setLoading", true, { root: true });
            commit(
                "transcription/setLoading",
                { key: "characterCount", loading: true },
                { root: true },
            );
            await dispatch("fetchTranscriptionStats");
            commit("characters/setLoading", false, { root: true });
            commit(
                "transcription/setLoading",
                { key: "characterCount", loading: false },
                { root: true },
            );
        } catch (error) {
            commit("characters/setLoading", false, { root: true });
            commit(
                "transcription/setLoading",
                { key: "characterCount", loading: false },
                { root: true },
            );
            dispatch("alerts/addError", error, { root: true });
        }
    },
    /**
     * Close the "delete document" modal.
     */
    closeDeleteModal({ commit }) {
        commit("setDeleteModalOpen", false);
    },
    /**
     * Close the "edit/delete document" menu.
     */
    closeDocumentMenu({ commit }) {
        commit("setMenuOpen", false);
    },
    /**
     * Close the "edit document" modal and clear out state.
     */
    closeEditModal({ commit, state }) {
        commit("setEditModalOpen", false);
        commit(
            "forms/setFormState",
            {
                form: "editDocument",
                formState: {
                    linePosition: state.linePosition,
                    mainScript: state.mainScript,
                    metadata: state.metadata,
                    name: state.name,
                    readDirection: state.readDirection,
                    tags: state.tags.map((tag) => tag.pk),
                    tagName: "",
                },
            },
            { root: true },
        );
    },
    /**
     * Close the "add group or user" modal and clear out state.
     */
    closeShareModal({ commit, dispatch }) {
        commit("setShareModalOpen", false);
        dispatch("forms/clearForm", "share", { root: true });
    },
    /**
     * Handle the user overwriting existing segmentation
     */
    async confirmOverwriteWarning({ commit, dispatch, rootState, state }) {
        try {
            commit("setLoading", { key: "document", loading: true });
            await dispatch(
                "tasks/segmentDocument",
                {
                    documentId: state.id,
                    parts: rootState.images.selectedParts || [],
                },
                { root: true },
            );
            dispatch("tasks/closeModal", "overwriteWarning", { root: true });
            dispatch("tasks/closeModal", "segment", { root: true });
            dispatch({ type: "sidebar/closeSidebar" }, { root: true });
            commit("setLoading", { key: "document", loading: false });
            // show toast alert on success
            dispatch(
                "alerts/add",
                {
                    color: "success",
                    message: "Segmentation queued successfully",
                },
                { root: true },
            );
        } catch (error) {
            commit("setLoading", { key: "document", loading: false });
            dispatch("alerts/addError", error, { root: true });
        }
    },
    /**
     * Handle confirming image cancellation by closing the modal, displaying
     * a relevant message, and reloading images.
     */
    async confirmImageCancelWarning({ commit, dispatch, rootState }) {
        if (rootState?.forms?.import?.imagesComplete === true) {
            // success message if ALL images imported successfully
            dispatch(
                "alerts/add",
                { color: "success", message: "Images imported successfully" },
                { root: true },
            );
        } else {
            // otherwise, message that import has been canceled
            dispatch(
                "alerts/add",
                { color: "text", message: "Image import canceled" },
                { root: true },
            );
        }
        // close modals and sidebar
        dispatch("tasks/closeModal", "imageCancelWarning", { root: true });
        dispatch("tasks/closeModal", "import", { root: true });
        dispatch({ type: "sidebar/closeSidebar" }, { root: true });
        // reload images
        commit("setLoading", { key: "parts", loading: true });
        await dispatch("fetchDocumentParts");
        commit("setLoading", { key: "parts", loading: false });
    },
    /**
     * Delete the current document.
     */
    async deleteDocument({ dispatch, commit, state }) {
        commit("setLoading", { key: "document", loading: true });
        try {
            await deleteDocument({ documentId: state.id });
            dispatch(
                "alerts/add",
                {
                    color: "success",
                    message: "Document deleted successfully",
                },
                { root: true },
            );
            commit("setDeleteModalOpen", false);
            // redirect to project on delete
            window.location = `/project/${state.projectSlug}`;
        } catch (error) {
            dispatch("alerts/addError", error, { root: true });
        }
        commit("setLoading", { key: "document", loading: false });
    },
    /**
     * Fetch the current document.
     */
    async fetchDocument({ commit, state, dispatch, rootState }) {
        // set all loading
        Object.keys(state.loading).map((key) =>
            commit("setLoading", { key, loading: true }),
        );
        commit("characters/setLoading", true, { root: true });
        // fetch document
        const { data } = await retrieveDocument(state.id);
        if (data) {
            commit("setLastModified", data.updated_at);
            commit("setMainScript", data.main_script);
            commit("setReadDirection", data.read_direction);
            commit("setLinePosition", data.line_offset);
            commit("setName", data.name);
            commit("setPartsCount", data.parts_count);
            commit("setProjectSlug", data.project);
            commit("setProjectId", data.project_id);
            commit("setProjectName", data.project_name);
            await commit("setRegionTypes", [
                ...data.valid_block_types,
                { pk: "Undefined", name: "(Undefined region type)" },
                { pk: "Orphan", name: "(Orphan lines)" },
            ]);
            // select all region types on forms that have that key
            Object.keys(forms)
                .filter((form) =>
                    Object.prototype.hasOwnProperty.call(
                        forms[form],
                        "regionTypes",
                    ),
                )
                .forEach((form) => {
                    commit(
                        "forms/setFieldValue",
                        {
                            form,
                            field: "regionTypes",
                            value: state.regionTypes.map((rt) =>
                                rt.pk.toString(),
                            ),
                        },
                        { root: true },
                    );
                });
            commit("setSharedWithGroups", data.shared_with_groups);
            commit("setSharedWithUsers", data.shared_with_users);
            commit(
                "setTags",
                data.tags?.map((tag) => ({
                    ...tag,
                    variant: tagColorToVariant(tag.color),
                })),
            );
            // set form state for the edit modal
            commit(
                "forms/setFormState",
                {
                    form: "editDocument",
                    formState: {
                        linePosition: data.line_offset,
                        mainScript: data.main_script,
                        metadata: state.metadata,
                        name: data.name,
                        readDirection: data.read_direction,
                        tags: state.tags.map((tag) => tag.pk),
                        tagName: "",
                    },
                },
                { root: true },
            );
            // set default text direction for the segment form
            commit(
                "forms/setFieldValue",
                {
                    form: "segment",
                    field: "textDirection",
                    value:
                        data.read_direction === "rtl"
                            ? "horizontal-rl"
                            : "horizontal-lr",
                },
                { root: true },
            );

            // kick off the document statistics fetching
            try {
                commit("ontology/setLoading", true, { root: true });
                await dispatch("fetchDocumentStats");
                commit("ontology/setLoading", false, { root: true });
            } catch (error) {
                commit("ontology/setLoading", false, { root: true });
                dispatch("alerts/addError", error, { root: true });
            }

            if (data.parts_count > 0) {
                // kickoff parts fetch
                try {
                    commit("setLoading", { key: "parts", loading: true });
                    await dispatch("fetchDocumentParts");
                    commit("setLoading", { key: "parts", loading: false });
                } catch (error) {
                    commit("setLoading", { key: "parts", loading: false });
                    dispatch("alerts/addError", error, { root: true });
                }
            } else {
                commit("setLoading", { key: "parts", loading: false });
            }
            if (data.transcriptions?.length) {
                // set transcription list to non-archived transcriptions
                const transcriptions = data.transcriptions?.filter(
                    (t) => !t.archived,
                );
                commit("setTranscriptions", transcriptions);
                // select the first one in the list if none selected already
                if (!rootState.transcription.selectedTranscription) {
                    commit(
                        "transcription/setSelectedTranscription",
                        transcriptions[0].pk,
                        { root: true },
                    );
                    const { lines_count } = transcriptions[0];
                    commit("transcription/setLineCount", lines_count, {
                        root: true,
                    });
                }

                // kick off the transcription statistics fetching
                try {
                    commit(
                        "transcription/setLoading",
                        { key: "characterCount", loading: true },
                        { root: true },
                    );
                    await dispatch("fetchTranscriptionStats");
                    commit(
                        "transcription/setLoading",
                        { key: "characterCount", loading: false },
                        { root: true },
                    );
                    commit("characters/setLoading", false, { root: true });
                } catch (error) {
                    commit(
                        "transcription/setLoading",
                        { key: "characterCount", loading: false },
                        { root: true },
                    );
                    commit("characters/setLoading", false, { root: true });
                    dispatch("alerts/addError", error, { root: true });
                }
            }
            if (data.project_id) {
                // set project id and fetch all document tags on the project
                try {
                    await commit("project/setId", data.project_id, {
                        root: true,
                    });
                    await dispatch(
                        { type: "project/fetchProjectDocumentTags" },
                        { root: true },
                    );
                } catch (error) {
                    dispatch("alerts/addError", error, { root: true });
                }
            }
        } else {
            commit("setLoading", { key: "document", loading: false });
            throw new Error("Unable to retrieve document");
        }
        commit("setLoading", { key: "document", loading: false });

        // fetch scripts, metadata, tasks, models, textual witnesses
        await dispatch({ type: "project/fetchScripts" }, { root: true });
        await dispatch("fetchDocumentMetadata");
        await dispatch("fetchDocumentTasks");
        await dispatch("fetchDocumentModels");
        await dispatch({ type: "user/fetchSegmentModels" }, { root: true });
        await dispatch({ type: "user/fetchRecognizeModels" }, { root: true });
        await dispatch("fetchTextualWitnesses");
    },
    /**
     * Fetch the current document's metadata.
     */
    async fetchDocumentMetadata({ commit, state }) {
        const { data } = await retrieveDocumentMetadata(state.id);
        if (data?.results) {
            commit("setMetadata", data.results);
            commit(
                "forms/setFieldValue",
                {
                    form: "editDocument",
                    field: "metadata",
                    value: data.results,
                },
                { root: true },
            );
        } else {
            throw new Error("Unable to retrieve document metadata");
        }
    },
    /**
     * Fetch the current document's models.
     */
    async fetchDocumentModels({ commit, state }) {
        commit("setLoading", { key: "models", loading: true });
        let models = [];
        const { data } = await retrieveDocumentModels(state.id);
        if (!data?.results)
            throw new Error("Unable to retrieve document models");
        models = data.results;
        let nextPage = data.next;
        while (nextPage) {
            const res = await axios.get(nextPage);
            nextPage = res.data.next;
            models = [...models, ...res.data.results];
        }
        commit("setModels", models);
        commit("setLoading", { key: "models", loading: false });
    },
    /**
     * Fetch the current document's most recent images with thumbnails.
     */
    async fetchDocumentParts({ commit, state }) {
        const { data } = await retrieveDocumentParts({
            documentId: state.id,
            field: "updated_at",
            direction: -1,
        });
        if (data?.results) {
            commit(
                "setParts",
                data.results.map((part) => ({
                    ...part,
                    title: `${part.title} - ${part.filename}`,
                    thumbnail: part.image?.thumbnails?.card,
                    href: `/document/${state.id}/part/${part.pk}/edit/`,
                })),
            );
        } else {
            throw new Error("Unable to retrieve document images");
        }
    },
    /**
     * Fetch page 1 of the current document's most recent tasks.
     */
    async fetchDocumentTasks({ commit, state }) {
        commit("setLoading", { key: "tasks", loading: true });
        const { data } = await retrieveDocumentTasks({ documentId: state.id });
        commit("setLoading", { key: "tasks", loading: false });
        if (data?.results) {
            commit("setTasks", data.results);
        } else {
            throw new Error("Unable to retrieve document tasks");
        }
    },
    /**
     * Fetch the most recent tasks, but throttle the fetch so it only happens once per 1000ms.
     */
    fetchDocumentTasksThrottled({ dispatch }) {
        throttle(function* () {
            yield dispatch("fetchDocumentTasks");
        });
    },
    /**
     * Fetch existing textual witnesses for use in alignment.
     */
    async fetchTextualWitnesses({ commit }) {
        const { data } = await retrieveTextualWitnesses();
        if (data?.results) {
            commit("setTextualWitnesses", data.results);
        } else {
            throw new Error("Unable to retrieve textual witnesses");
        }
    },
    /**
     * Fetch the current transcription's characters, given this document's id from state,
     * plus sorting params from characters Vuex store.
     */
    async fetchTranscriptionStats({ commit, state, rootState }) {
        const { data } = await retrieveTranscriptionStats({
            documentId: state.id,
            transcriptionId: rootState.transcription.selectedTranscription,
            field: rootState.characters.sortState?.field,
            direction: rootState.characters.sortState?.direction,
        });
        let { characters, line_count } = data;
        commit("characters/setCharacters", characters, { root: true });
        commit("transcription/setLineCount", line_count, { root: true });
        commit(
            "transcription/setCharacterCount",
            characters.reduce((accumulator, c) => accumulator + c.frequency, 0),
            { root: true },
        );
    },
    /**
     * Retrieve statistics about the document ontology
     */
    async fetchDocumentStats({ commit, rootState, state }) {
        const { data } = await retrieveDocumentStats({
            documentId: state.id,
            sortField: rootState.ontology.sortState?.field,
            sortDirection: rootState.ontology.sortState?.direction,
        });
        if (data) {
            commit("setTypes", {
                regions: data.regions.map((r) => (
                    {...r, name: r.typology_name || "None" }
                )),
                lines: data.lines.map((l) => (
                    {...l, name: l.typology_name || "None" }
                )),
                text: data.text_annotations.map((t) => (
                    {...t, name: t.taxonomy_name || "None"}
                )),
                image: data.image_annotations.map((i) => (
                    {...i, name: i.taxonomy_name || "None"}
                )),
            });
        } else {
            throw new Error("Unable to retrieve ontology");
        }
    },
    /**
     * Refresh images and transcriptions when import is complete
     */
    async handleImportDone({ commit, dispatch }) {
        try {
            // refresh images on import:done
            commit("setLoading", { key: "parts", loading: true });
            await dispatch("fetchDocumentParts");
            commit("setLoading", { key: "parts", loading: false });
            // refresh transcriptions on import:done
            commit("setLoading", { key: "document", loading: true });
            await dispatch("refreshTranscriptions");
            commit("setLoading", { key: "document", loading: false });
        } catch (error) {
            dispatch("alerts/addError", error, { root: true });
            commit("setLoading", { key: "parts", loading: false });
            commit("setLoading", { key: "document", loading: false });
        }
    },
    /**
     * Handle submitting the alignment modal. Queue the task and close the modal.
     */
    async handleSubmitAlign({ commit, dispatch, rootState, state }) {
        try {
            commit("setLoading", { key: "document", loading: true });
            await dispatch(
                "tasks/alignDocument",
                {
                    documentId: state.id,
                    parts: rootState.images.selectedParts || [],
                },
                { root: true },
            );
            dispatch("tasks/closeModal", "align", { root: true });
            dispatch({ type: "sidebar/closeSidebar" }, { root: true });
            commit("setLoading", { key: "document", loading: false });
            // show toast alert on success
            dispatch(
                "alerts/add",
                {
                    color: "success",
                    message: "Alignment queued successfully",
                },
                { root: true },
            );
        } catch (error) {
            dispatch("alerts/addError", error, { root: true });
            commit("setLoading", { key: "document", loading: false });
        }
    },
    /**
     * Handle submitting the export modal. Queue the task and close the modal.
     */
    async handleSubmitExport({ commit, dispatch, rootState, state }) {
        try {
            commit("setLoading", { key: "document", loading: true });
            await dispatch(
                "tasks/exportDocument",
                {
                    documentId: state.id,
                    parts: rootState.images.selectedParts || [],
                },
                { root: true },
            );
            dispatch("tasks/closeModal", "export", { root: true });
            dispatch({ type: "sidebar/closeSidebar" }, { root: true });
            commit("setLoading", { key: "document", loading: false });
            // show toast alert on success
            dispatch(
                "alerts/add",
                {
                    color: "success",
                    message: "Export queued successfully",
                },
                { root: true },
            );
        } catch (error) {
            dispatch("alerts/addError", error, { root: true });
            commit("setLoading", { key: "document", loading: false });
        }
    },
    /**
     * Handle submitting the import modal. Queue the task and close the modal.
     */
    async handleSubmitImport({ commit, dispatch, rootState, state }) {
        try {
            commit("setLoading", { key: "document", loading: true });
            const importMode = rootState?.forms?.import?.mode;
            await dispatch("tasks/importImagesOrTranscription", state.id, {
                root: true,
            });
            dispatch("tasks/closeModal", "import", { root: true });
            dispatch({ type: "sidebar/closeSidebar" }, { root: true });
            commit("setLoading", { key: "document", loading: false });
            // show toast alert on success
            dispatch(
                "alerts/add",
                {
                    color: "success",
                    message:
                        importMode === "images"
                            ? "Images imported successfully"
                            : "Import queued successfully. It may take time for images to appear.",
                    delay: 4000,
                },
                { root: true },
            );
            if (importMode === "images") {
                commit("setLoading", { key: "parts", loading: true });
                await dispatch("fetchDocumentParts");
                commit("setLoading", { key: "parts", loading: false });
            }
        } catch (error) {
            commit("setLoading", { key: "document", loading: false });
            dispatch("alerts/addError", error, { root: true });
        }
    },
    /**
     * Handle submitting the segmentation modal. Open the confirm overwrite modal if overwrite
     * is checked, otherwise just queue the segmentation task and close the modal.
     */
    async handleSubmitSegmentation({ commit, dispatch, state, rootState }) {
        if (rootState?.forms?.segment?.overwrite === true) {
            dispatch("tasks/openModal", "overwriteWarning", { root: true });
        } else {
            commit("setLoading", { key: "document", loading: true });
            try {
                await dispatch(
                    "tasks/segmentDocument",
                    {
                        documentId: state.id,
                        parts: rootState.images.selectedParts || [],
                    },
                    { root: true },
                );
                dispatch("tasks/closeModal", "segment", { root: true });
                // set default text direction for the segment form
                commit(
                    "forms/setFieldValue",
                    {
                        form: "segment",
                        field: "textDirection",
                        value:
                            state.readDirection === "rtl"
                                ? "horizontal-rl"
                                : "horizontal-lr",
                    },
                    { root: true },
                );
                dispatch({ type: "sidebar/closeSidebar" }, { root: true });
                commit("setLoading", { key: "document", loading: false });
                // show toast alert on success
                dispatch(
                    "alerts/add",
                    {
                        color: "success",
                        message: "Segmentation queued successfully",
                    },
                    { root: true },
                );
            } catch (error) {
                commit("setLoading", { key: "document", loading: false });
                dispatch("alerts/addError", error, { root: true });
            }
        }
    },
    /**
     * Handle submitting the transcribe modal: just queue the task and close the modal.
     */
    async handleSubmitTranscribe({ commit, dispatch, rootState, state }) {
        try {
            commit("setLoading", { key: "document", loading: true });
            await dispatch(
                "tasks/transcribeDocument",
                {
                    documentId: state.id,
                    parts: rootState.images.selectedParts || [],
                },
                { root: true },
            );
            dispatch("tasks/closeModal", "transcribe", { root: true });
            dispatch({ type: "sidebar/closeSidebar" }, { root: true });
            await dispatch("refreshTranscriptions");
            commit("setLoading", { key: "document", loading: false });
            // show toast alert on success
            dispatch(
                "alerts/add",
                {
                    color: "success",
                    message: "Transcription queued successfully",
                },
                { root: true },
            );
        } catch (error) {
            commit("setLoading", { key: "document", loading: false });
            dispatch("alerts/addError", error, { root: true });
        }
    },
    /**
     * Open the "delete document" modal.
     */
    openDeleteModal({ commit }) {
        commit("setDeleteModalOpen", true);
    },
    /**
     * Open the "edit/delete document" menu.
     */
    openDocumentMenu({ commit }) {
        commit("setMenuOpen", true);
    },
    /**
     * Open the "edit document" modal.
     */
    openEditModal({ commit }) {
        commit("setEditModalOpen", true);
    },
    /**
     * Open the "groups and users" modal.
     */
    openShareModal({ commit }) {
        commit("setShareModalOpen", true);
    },
    /**
     * Fetch the current document, but only update the transcriptions and don't kick off
     * other fetches.
     */
    async refreshTranscriptions({ commit, state }) {
        // fetch document
        const { data } = await retrieveDocument(state.id);

        if (data?.transcriptions) {
            // set transcription list to non-archived transcriptions
            const transcriptions = data.transcriptions?.filter(
                (t) => !t.archived,
            );
            commit("setTranscriptions", transcriptions);
        } else {
            throw new Error("Unable to fetch transcriptions");
        }
    },
    /**
     * Save changes to the document made in the edit modal.
     */
    async saveDocument({ commit, dispatch, rootState, state }) {
        commit("setLoading", { key: "document", loading: true });
        // get form state
        const {
            linePosition,
            mainScript,
            metadata,
            name,
            readDirection,
            tags,
        } = rootState.forms.editDocument;
        // split modified metadata by operation
        const { metadataToCreate, metadataToUpdate, metadataToDelete } =
            getMetadataCRUD({
                stateMetadata: state.metadata,
                formMetadata: metadata,
            });
        try {
            const [documentResponse, ...metadataResponses] = await Promise.all([
                // update the document
                editDocument(state.id, {
                    linePosition,
                    mainScript,
                    name,
                    readDirection,
                    project: state.projectSlug,
                    tags,
                }),
                // create, update, delete metadata as needed
                ...metadataToCreate.map((metadatum) =>
                    createDocumentMetadata({
                        documentId: state.id,
                        metadatum,
                    }),
                ),
                ...metadataToUpdate.map((metadatum) =>
                    updateDocumentMetadata({
                        documentId: state.id,
                        metadatum,
                    }),
                ),
                ...metadataToDelete.map((m) =>
                    deleteDocumentMetadata({
                        documentId: state.id,
                        metadatumId: m.pk,
                    }),
                ),
            ]);
            // update state for metadata responses
            metadataResponses
                .filter((r) => !!r)
                .forEach((response) => {
                    if (response.status === 200) {
                        // updated
                        const { data } = response;
                        commit("updateMetadatum", data);
                    } else if (response.status === 201) {
                        // created
                        const { data } = response;
                        commit("addMetadatum", data);
                    } else if (response.status === 204) {
                        // deleted
                        const { request } = response;
                        const splitURL = request?.responseURL.split("/");
                        const pk = splitURL[splitURL.length - 2];
                        commit("removeMetadatum", pk);
                    } else {
                        throw new Error("Error updating metadata");
                    }
                });
            // update state for document response
            if (documentResponse?.data) {
                commit("setName", name);
                commit("setLinePosition", linePosition);
                commit("setMainScript", mainScript);
                commit("setReadDirection", readDirection);
                commit(
                    "setTags",
                    documentResponse.data.tags.map((tag) => ({
                        ...tag,
                        variant: tagColorToVariant(tag.color),
                    })),
                );
                commit("setEditModalOpen", false);
            } else {
                throw new Error("Unable to save document");
            }
            // show toast alert on success
            dispatch(
                "alerts/add",
                {
                    color: "success",
                    message: "Document updated successfully",
                },
                { root: true },
            );
        } catch (error) {
            commit("setLoading", { key: "document", loading: false });
            dispatch("alerts/addError", error, { root: true });
        }
        commit("setLoading", { key: "document", loading: false });
    },
    /**
     * Set the ID of the document on the state (happens immediately on page load).
     */
    setId({ commit }, id) {
        commit("setId", id);
    },
    /**
     * Set the loading state.
     */
    setLoading({ commit }, { key, loading }) {
        commit("setLoading", { key, loading });
    },
    /**
     * Send a POST request to share the document with users and groups from the share form.
     */
    async shareDocument({ commit, dispatch, state, rootState }) {
        commit("setLoading", { key: "document", loading: true });
        const { user, group } = rootState.forms.share;
        const params = { documentId: state.id };
        if (user) params["user"] = user;
        else if (group) params["group"] = group;
        try {
            const { data } = await shareDocument(params);
            if (data) {
                // show toast alert on success
                dispatch(
                    "alerts/add",
                    {
                        color: "success",
                        message: `${
                            user ? "User" : "Group"
                        } added successfully`,
                    },
                    { root: true },
                );
                // update share data on frontend
                commit("setSharedWithGroups", data.shared_with_groups);
                commit("setSharedWithUsers", data.shared_with_users);
            } else {
                throw new Error("Unable to add user or group.");
            }
        } catch (error) {
            commit("setLoading", { key: "document", loading: false });
            dispatch("alerts/addError", error, { root: true });
        }
        commit("setLoading", { key: "document", loading: false });
        dispatch("closeShareModal");
    },
    /**
     * Change the characters sort field and perform another fetch for characters.
     */
    async sortCharacters({ commit, dispatch }, field) {
        let direction = 1;
        if (field === "frequency") {
            direction = -1;
        }
        commit("characters/setSortState", { field, direction }, { root: true });
        try {
            commit("characters/setLoading", true, { root: true });
            await dispatch("fetchTranscriptionStats");
            commit("characters/setLoading", false, { root: true });
        } catch (error) {
            commit("characters/setLoading", false, { root: true });
            dispatch("alerts/addError", error, { root: true });
        }
    },
    /**
     * Update a part's workflow status.
     */
    updatePartTaskStatus({ commit, state }, { id, process, status }) {
        if (id) {
            const part = structuredClone(
                state.parts.find((p) => p.pk.toString() === id.toString()),
            );
            if (part) {
                part.workflow[process] =
                    status === "canceled" ? "error" : status;
                commit("updatePart", part);
            }
        }
    },
};

const mutations = {
    addPart(state, part) {
        state.parts.push(part);
    },
    addMetadatum(state, metadatum) {
        const metadata = structuredClone(state.metadata);
        metadata.push(metadatum);
        state.metadata = metadata;
    },
    removeMetadatum(state, removePk) {
        const clone = structuredClone(state.metadata);
        state.metadata = clone.filter(
            (metadatum) => metadatum.pk.toString() !== removePk.toString(),
        );
    },
    removePart(state, removePk) {
        const clone = structuredClone(state.parts);
        state.parts = clone.filter(
            (part) => part.pk.toString() !== removePk.toString(),
        );
    },
    setDeleteModalOpen(state, open) {
        state.deleteModalOpen = open;
    },
    setEditModalOpen(state, open) {
        state.editModalOpen = open;
    },
    setId(state, id) {
        state.id = id;
    },
    setLastModified(state, lastModified) {
        state.lastModified = lastModified;
    },
    setLinePosition(state, linePosition) {
        state.linePosition = linePosition;
    },
    setLoading(state, { key, loading }) {
        const clone = structuredClone(state.loading);
        clone[key] = loading;
        state.loading = clone;
    },
    setMainScript(state, mainScript) {
        state.mainScript = mainScript;
    },
    setMenuOpen(state, open) {
        state.menuOpen = open;
    },
    setMetadata(state, metadata) {
        state.metadata = metadata;
    },
    setModels(state, models) {
        state.models = models;
    },
    setName(state, name) {
        state.name = name;
    },
    setParts(state, parts) {
        state.parts = parts;
    },
    setPartsCount(state, partsCount) {
        state.partsCount = partsCount;
    },
    setProjectId(state, projectId) {
        state.projectId = projectId;
    },
    setProjectSlug(state, projectSlug) {
        state.projectSlug = projectSlug;
    },
    setProjectName(state, projectName) {
        state.projectName = projectName;
    },
    setReadDirection(state, readDirection) {
        state.readDirection = readDirection;
    },
    setRegionTypes(state, regionTypes) {
        state.regionTypes = regionTypes;
    },
    setSharedWithGroups(state, groups) {
        state.sharedWithGroups = groups;
    },
    setSharedWithUsers(state, users) {
        state.sharedWithUsers = users;
    },
    setShareModalOpen(state, open) {
        state.shareModalOpen = open;
    },
    setTasks(state, tasks) {
        state.tasks = tasks;
    },
    setTags(state, tags) {
        state.tags = tags;
    },
    setTextualWitnesses(state, textualWitnesses) {
        state.textualWitnesses = textualWitnesses;
    },
    setTranscriptions(state, transcriptions) {
        state.transcriptions = transcriptions;
    },
    setTypes(state, types) {
        state.types = types;
    },
    updateMetadatum(state, metadatumToUpdate) {
        const metadata = structuredClone(state.metadata).map((m) => {
            if (m.pk.toString() === metadatumToUpdate.pk.toString()) {
                return metadatumToUpdate;
            }
            return m;
        });
        state.metadata = metadata;
    },
    updatePart(state, partToUpdate) {
        const parts = structuredClone(state.parts).map((p) => {
            if (p.pk.toString() === partToUpdate.pk.toString()) {
                return partToUpdate;
            }
            return p;
        });
        state.parts = parts;
    },
};

export default {
    namespaced: true,
    state,
    getters,
    actions,
    mutations,
};
