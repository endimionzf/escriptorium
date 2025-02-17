import * as api from "../api";
import {
    createComponentTaxonomy,
    retrieveComponentTaxonomies,
    retrieveDefaultOntology,
    createType,
    deleteType,
    updateDocumentOntology,
    updateType,
    createAnnotationType,
    updateAnnotationType,
    deleteAnnotationType,
    updateComponentTaxonomy,
    deleteComponentTaxonomy,
} from "../../api";

export const initialState = () => ({
    id: null,
    name: "",
    projectSlug: "",
    projectName: "",
    partsCount: 0,
    defaultTextDirection: null,
    mainTextDirection: null,
    readDirection: null,
    types: {},
    blockShortcuts: false,

    annotationTaxonomies: {},
    componentTaxonomies: [],

    // Manage panels visibility through booleans
    // Those values are initially populated by localStorage
    visible_panels: {
        source: userProfile.get("visible-panels")
            ? userProfile.get("visible-panels").source
            : false,
        segmentation: userProfile.get("visible-panels")
            ? userProfile.get("visible-panels").segmentation
            : true,
        visualisation: userProfile.get("visible-panels")
            ? userProfile.get("visible-panels").visualisation
            : true,
        diplomatic: userProfile.get("visible-panels")
            ? userProfile.get("visible-panels").diplomatic
            : false,
        metadata: userProfile.get("visible-panels")
            ? userProfile.get("visible-panels").metadata
            : false,
    },

    // "New UI" version of visible_panels management
    // get from userProfile, or by default, [segmentation, visualisation]
    editorPanels: userProfile.get("editor-panels")
        ? userProfile.get("editor-panels")
        : ["segmentation", "visualisation"],

    // Confidence overlay visibility (global, from document settings)
    confidenceVisible: false,
    // Confidence overlay visibility (local, new UI)
    confidenceVizOn: false,
    // exponential scale factor for confidence overlay
    confidenceScale: 4,

    enabledVKs: userProfile.get("VK-enabled")
        ? userProfile.get("VK-enabled")
        : [],

    defaultTypes: {},
    loading: false,
    segmentationOpened: false,
});

export const mutations = {
    addEditorPanel(state, panel) {
        const editorPanels = structuredClone(state.editorPanels);
        editorPanels.push(panel);
        state.editorPanels = editorPanels;
        // Persist final value in user profile
        userProfile.set("editor-panels", editorPanels);
    },
    setId(state, id) {
        state.id = id;
    },
    setName(state, name) {
        state.name = name;
    },
    setDefaultTextDirection(state, direction) {
        state.defaultTextDirection = direction;
    },
    setMainTextDirection(state, direction) {
        state.mainTextDirection = direction;
    },
    setReadDirection(state, direction) {
        state.readDirection = direction;
    },
    setTypes(state, types) {
        state.types = types;
    },
    setPartsCount(state, count) {
        state.partsCount = count;
    },
    setBlockShortcuts(state, block) {
        state.blockShortcuts = block;
    },
    setVisiblePanels(state, payload) {
        state.visible_panels = Object.assign({}, state.visible_panels, payload);
    },
    setAnnotationTaxonomies(state, { type, taxos }) {
        const taxosClone = structuredClone(state.annotationTaxonomies);
        taxosClone[type] = taxos;
        state.annotationTaxonomies = taxosClone;
    },
    setComponentTaxonomies(state, taxos) {
        state.componentTaxonomies = taxos;
    },
    setEnabledVKs(state, vks) {
        state.enabledVKs = Object.assign([], state.enabledVKs, vks);
    },
    setConfidenceScale(state, scale) {
        state.confidenceScale = scale;
    },
    setConfidenceVizGloballyEnabled(state, enabled) {
        state.confidenceVisible = enabled;
    },
    setProjectSlug(state, projectSlug) {
        state.projectSlug = projectSlug;
    },
    setProjectName(state, projectName) {
        state.projectName = projectName;
    },
    setSegmentationOpened(state) {
        state.segmentationOpened = true;
    },
    switchEditorPanel(state, { index, panel }) {
        let editorPanels = structuredClone(state.editorPanels);
        if (editorPanels[index] !== panel) {
            // do nothing if it's the same panel
            if (editorPanels.includes(panel)) {
                // if it's open, replace panel at its index with this panel
                const thisPanel = editorPanels[index];
                const thatIndex = editorPanels.indexOf(panel);
                editorPanels[thatIndex] = thisPanel;
            }
            editorPanels[index] = panel;
            state.editorPanels = editorPanels;
            // Persist final value in user profile
            userProfile.set("editor-panels", editorPanels);
        }
    },
    removeEditorPanel(state, panel) {
        let editorPanels = structuredClone(state.editorPanels).filter(
            (editorPanel) => editorPanel.toString() !== panel.toString(),
        );
        state.editorPanels = editorPanels;
        // Persist final value in user profile
        userProfile.set("editor-panels", editorPanels);
        if (editorPanels.includes("segmentation")) {
            // FIXME: This is a temporary solution until the issue
            // with the segmentation canvas shifting is resolved.
            window.location.reload();
        }
    },
    reset(state) {
        Object.assign(state, initialState());
    },
    setDefaultTypes(state, types) {
        state.defaultTypes = types;
    },
    setLoading(state, loading) {
        state.loading = loading;
    },
    toggleConfidenceVizOn(state) {
        state.confidenceVizOn = !state.confidenceVizOn;
    },
};

export const actions = {
    async fetchDocument({ state, commit, dispatch }) {
        const resp = await api.retrieveDocument(state.id);
        let data = resp.data;
        var valid_part_types = data.valid_part_types;
        valid_part_types.unshift({ pk: null, name: "Element" });

        // set transcriptions state
        commit("transcriptions/set", data.transcriptions, { root: true });
        // set transcriptions form state
        commit(
            "forms/setFormState",
            {
                form: "transcriptionManagement",
                formState: { transcriptions: data.transcriptions },
            },
            { root: true },
        );

        let page = 1;
        var img_taxos = [];
        while (page) {
            let resp = await api.retrieveAnnotationTaxonomies(
                data.pk,
                "image",
                page,
            );
            img_taxos = img_taxos.concat(resp.data.results);
            if (resp.data.next) page++;
            else page = null;
        }
        commit("setAnnotationTaxonomies", { type: "image", taxos: img_taxos });

        page = 1;
        var text_taxos = [];
        while (page) {
            let resp = await api.retrieveAnnotationTaxonomies(
                data.pk,
                "text",
                page,
            );
            text_taxos = text_taxos.concat(resp.data.results);
            if (resp.data.next) page++;
            else page = null;
        }
        commit("setAnnotationTaxonomies", { type: "text", taxos: text_taxos });

        // fetch annotation components
        page = 1;
        let componentTaxonomies = [];
        while (page) {
            let resp = await retrieveComponentTaxonomies(data.pk);
            componentTaxonomies = componentTaxonomies.concat(resp.data.results);
            if (resp.data.next) page++;
            else page = null;
        }
        commit("setComponentTaxonomies", componentTaxonomies);

        // set types on state
        const types = {
            regions: data.valid_block_types || [],
            lines: data.valid_line_types || [],
            parts: valid_part_types || [],
            text: text_taxos || [],
            image: img_taxos || [],
        };
        commit("setTypes", types);
        // set types form state
        commit(
            "forms/setFormState",
            {
                form: "ontology",
                formState: { ...types },
            },
            { root: true },
        );
        commit("setProjectSlug", data.project);
        commit("setProjectName", data.project_name);
        commit("setPartsCount", data.parts_count);
        commit("setConfidenceVizGloballyEnabled", data.show_confidence_viz);

        await dispatch("fetchDefaultTypes");
    },

    async togglePanel({ state, commit }, panel) {
        // Toggle the display of a single panel
        let update = {};
        update[panel] = !state.visible_panels[panel];
        commit("setVisiblePanels", update);

        // Persist final value in user profile
        userProfile.set("visible-panels", state.visible_panels);
    },

    async scaleConfidence({ commit }, scale) {
        commit("setConfidenceScale", scale);
    },

    /**
     * Add an editor panel by clicking the "add panel" button (new UI)
     */
    addEditorPanel({ state, commit, dispatch }, panel) {
        if (
            state.editorPanels.length < 3 &&
            !state.editorPanels.includes(panel)
        ) {
            // add to the end
            commit("addEditorPanel", panel);
            if (panel === "segmentation") {
                if (state.segmentationOpened) {
                    // FIXME: This is a temporary solution until the issue
                    // with the segmentation canvas shifting is resolved.
                    window.location.reload();
                } else {
                    commit("setSegmentationOpened");
                }
            }
        } else if (state.editorPanels.length >= 3) {
            dispatch("alerts/addError", "Cannot view more than three panels", {
                root: true,
            });
        }
    },

    /**
     * Create a new annotation component
     */
    async createComponent({ commit, dispatch, state, rootState }) {
        const { name, values } = rootState.forms.addComponent;
        const documentId = state.id;
        commit("setLoading", true);
        try {
            await createComponentTaxonomy({
                documentId,
                name,
                allowedValues: values ? values.split(",") : [],
            });
        } catch (err) {
            commit("setLoading", false);
            dispatch("alerts/addError", err, { root: true });
        }

        await dispatch("retrieveComponents");
        commit("setLoading", false);
    },

    /**
     * Helper method to retrieve the list of annotation components
     */
    async retrieveComponents({ commit, state }) {
        let page = 1;
        let componentTaxonomies = [];
        while (page) {
            const resp = await retrieveComponentTaxonomies(state.id);
            componentTaxonomies = componentTaxonomies.concat(resp.data.results);
            if (resp.data.next) page++;
            else page = null;
        }
        commit("document/setComponentTaxonomies", componentTaxonomies, {
            root: true,
        });
    },

    /**
     * Update an annotation component
     */
    async updateComponent({ commit, dispatch, rootState, state }) {
        const { name, pk, values } = rootState.forms.addComponent;
        const documentId = state.id;
        commit("setLoading", true);
        try {
            await updateComponentTaxonomy({
                documentId,
                pk,
                name,
                allowedValues: values ? values.split(",") : [],
            });
        } catch (err) {
            commit("setLoading", false);
            dispatch("alerts/addError", err, { root: true });
        }

        await dispatch("retrieveComponents");
        commit("setLoading", false);
    },

    /**
     * Delete an annotation component
     */
    async deleteComponent({ commit, dispatch, state }, component) {
        const { pk } = component;
        const documentId = state.id;
        commit("setLoading", true);
        try {
            await deleteComponentTaxonomy({ documentId, pk });
        } catch (err) {
            commit("setLoading", false);
            dispatch("alerts/addError", err, { root: true });
        }

        await dispatch("retrieveComponents");
        commit("setLoading", false);
    },

    /**
     * Fetch default types
     */
    async fetchDefaultTypes({ commit }) {
        let types = {};
        await Promise.all(
            ["regions", "lines", "parts"].map(async (category) => {
                const { data } = await retrieveDefaultOntology(category);
                if (data?.results) {
                    types[category] = data.results;
                }
                let noneType = { pk: null, name: "None" };
                if (category === "parts") noneType.name = "Element";
                types[category] = [noneType, ...types[category]];
                return;
            }),
        );
        commit("setDefaultTypes", types);
    },

    /**
     * Remove an editor panel by clicking the "add panel" button (new UI)
     */
    removeEditorPanel({ state, commit, dispatch }, panel) {
        if (state.editorPanels.length > 0) {
            // remove by name
            commit("removeEditorPanel", panel);
        } else {
            dispatch(
                "alerts/addError",
                "Must have at least one visible panel",
                {
                    root: true,
                },
            );
        }
    },

    async saveOntologyChanges({ commit, state, rootState }) {
        commit("setLoading", true);
        let typesToUpdate = {};
        let typesToDelete = {};
        let validTypes = {};
        // NOTE: colors were saved separately (local settings only), in the modal.
        await Promise.all(
            Object.entries(rootState.forms.ontology).map(
                async ([category, newTypes]) => {
                    const oldTypes = state.types[category] || [];
                    // default types: we can't make changes to them, but we can choose if they
                    // should be enabled or disabled for this document.
                    const defaultTypes = state.defaultTypes[category] || [];

                    // prepare types from form state
                    typesToUpdate[category] = [];
                    typesToDelete[category] = [];
                    validTypes[category] = [];
                    await Promise.all(
                        newTypes.map(async (type) => {
                            let typePk = type.pk;

                            // annotation types have some extra data
                            let annotationParams = null;
                            if (["image", "text"].includes(category)) {
                                annotationParams = {
                                    name: type.name,
                                    abbreviation: type.abbreviation,
                                    components: type.components?.map((c) => c.pk),
                                    has_comments: type.has_comments,
                                    marker_detail: type.marker_detail,
                                    marker_type: type.marker_type,
                                };
                                // only add this if it exists, serializer doesn't like it blank
                                if (type.typology?.name) {
                                    annotationParams["typology"] = type.typology;
                                }
                            }

                            // non-default types: create/queue for update
                            if (
                                !defaultTypes.find(
                                    (b) =>
                                        (!typePk && b.name === type.name) ||
                                        (typePk && typePk === b.pk),
                                )
                            ) {
                                let oldType = oldTypes.find((o) => o.pk === type.pk);
                                if (!typePk) {
                                    // create new types
                                    if (annotationParams) {
                                        // annotation types are document-scoped in API
                                        const { data } =
                                            await createAnnotationType({
                                                documentId: state.id,
                                                target: category,
                                                data: annotationParams,
                                            });
                                        typePk = data.pk;
                                    } else {
                                        const { data } = await createType(
                                            category,
                                            { name: type.name },
                                        );
                                        typePk = data.pk;
                                    }
                                } else if (oldType) {
                                    // update changed existing types (non-default)
                                    if (
                                        annotationParams &&
                                        (
                                            oldType.name !== type.name ||
                                            oldType.abbreviation !== type.abbreviation ||
                                            oldType.marker_type !== type.marker_type ||
                                            oldType.marker_detail !== type.marker_detail ||
                                            oldType.has_comments !== type.has_comments ||
                                            (!oldType.typology && type.typology) ||
                                            oldType.typology?.name !== type.typology?.name ||
                                            (!oldType.components && annotationParams.components) ||
                                            oldType.components?.some(
                                                (c) => !annotationParams.components?.includes(c.pk)
                                            ) ||
                                            annotationParams.components?.some(
                                                (c) => !oldType.components.map(
                                                    (oc) => oc.pk
                                                ).includes(c.pk)
                                            )
                                        )
                                    ) {
                                        await updateAnnotationType({
                                            documentId: state.id,
                                            typePk: type.pk,
                                            data: annotationParams,
                                        });
                                    } else if (oldType.name !== type.name) {
                                        await updateType(category, {
                                            typePk: type.pk,
                                            name: type.name,
                                        });
                                    }
                                }
                            }
                            if (typePk) {
                                // add type to valid types for this document
                                validTypes[category].push(typePk);
                            }
                            return Promise.resolve();
                        }),
                    );

                    // not in form types + not in default types = should be deleted
                    await Promise.all(
                        oldTypes
                            .filter((a) => !newTypes.find((b) => a.pk === b.pk))
                            .filter(
                                (a) => !defaultTypes.find((b) => a.pk === b.pk),
                            )
                            .map(
                                async (type) => {
                                    if (["image", "text"].includes(category)) {
                                        return await deleteAnnotationType({
                                            documentId: state.id,
                                            typePk: type.pk,
                                        });
                                    } else {
                                        return await deleteType(category, {
                                            typePk: type.pk,
                                        });
                                    }
                                }
                            ),
                    );
                },
            ),
        );
        // finally, set the valid types on the document
        const { data } = await updateDocumentOntology(state.id, {
            valid_line_types: validTypes["lines"],
            valid_part_types: validTypes["parts"],
            valid_block_types: validTypes["regions"],
        });

        let page = 1;
        var img_taxos = [];
        while (page) {
            let resp = await api.retrieveAnnotationTaxonomies(
                data.pk,
                "image",
                page,
            );
            img_taxos = img_taxos.concat(resp.data.results);
            if (resp.data.next) page++;
            else page = null;
        }
        commit("setAnnotationTaxonomies", { type: "image", taxos: img_taxos });

        page = 1;
        var text_taxos = [];
        while (page) {
            let resp = await api.retrieveAnnotationTaxonomies(
                data.pk,
                "text",
                page,
            );
            text_taxos = text_taxos.concat(resp.data.results);
            if (resp.data.next) page++;
            else page = null;
        }
        commit("setAnnotationTaxonomies", { type: "text", taxos: text_taxos });

        // fetch annotation components
        page = 1;
        let componentTaxonomies = [];
        while (page) {
            let resp = await retrieveComponentTaxonomies(data.pk);
            componentTaxonomies = componentTaxonomies.concat(resp.data.results);
            if (resp.data.next) page++;
            else page = null;
        }
        commit("setComponentTaxonomies", componentTaxonomies);

        // set types on state
        const types = {
            regions: data.valid_block_types || [],
            lines: data.valid_line_types || [],
            parts: data.valid_part_types || [],
            text: text_taxos || [],
            image: img_taxos || [],
        };
        commit("setTypes", types);
        commit(
            "forms/setFormState",
            {
                form: "ontology",
                formState: { ...types },
            },
            { root: true },
        );
        commit("setLoading", false);
    },

    /**
     * Switch an editor panel out for another one (new UI)
     */
    switchEditorPanel({ commit, state }, { index, panel }) {
        // handle switching out segmentation by reloading
        if (
            (panel === "segmentation" && state.segmentationOpened) ||
            (state.editorPanels?.includes("segmentation") &&
                (state.editorPanels[index] === "segmentation" ||
                    panel === "segmentation"))
        ) {
            commit("switchEditorPanel", { index, panel });
            // FIXME: This is a temporary solution until the issue
            // with the segmentation canvas shifting is resolved.
            window.location.reload();
        } else {
            commit("switchEditorPanel", { index, panel });
            if (state.editorPanels.includes("segmentation")) {
                commit("setSegmentationOpened");
            }
        }
    },

    /**
     * Toggle the confidence visualization locally
     */
    toggleConfidence({ commit }) {
        commit("toggleConfidenceVizOn");
    },
};

export default {
    namespaced: true,
    state: initialState(),
    mutations,
    actions,
};
