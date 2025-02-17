<template>
    <EscrModal
        class="escr-export-modal"
    >
        <template #modal-header>
            <h2>Export {{ scope }}</h2>
            <EscrButton
                color="text"
                :on-click="onCancel"
                size="small"
            >
                <template #button-icon>
                    <XIcon />
                </template>
            </EscrButton>
        </template>
        <template #modal-content>
            <DropdownField
                label="Transcription"
                :disabled="disabled || !transcriptions"
                :options="transcriptionOptions"
                :on-change="handleTranscriptionChange"
                required
            />
            <DropdownField
                label="File Format"
                :disabled="disabled"
                :options="fileFormatOptions"
                :on-change="handleFileFormatChange"
                required
            />
            <div class="escr-form-field escr-include-images-field escr-checkbox-field">
                <label>
                    <input
                        type="checkbox"
                        value="include-images"
                        :checked="includeImages === true && fileFormat !== 'text'"
                        :disabled="fileFormat === 'text'"
                        @change="handleIncludeImagesChange"
                    >
                    Include images
                </label>
                <span class="escr-help-text">
                    Will significantly increase the time to produce and download the export.
                </span>
            </div>

            <div class="escr-form-field escr-include-characters-field escr-checkbox-field">
                <label>
                    <input
                        type="checkbox"
                        value="include-characters"
                        @change="handleIncludeCharactersChange"
                    >
                    Include Characters
                </label>
                <span class="escr-help-text">
                    This data is only present for transcriptions coming from automatic recognition
                    and is invalidated by manual edition.
                </span>
            </div>

            <ArrayField
                :on-change="handleRegionTypesChange"
                :options="regionTypesOptions"
                class="escr-region-types"
                help-text="Select region types to include in the export."
                label="Region Types"
            />
        </template>
        <template #modal-actions>
            <EscrButton
                color="outline-primary"
                label="Cancel"
                :on-click="onCancel"
                :disabled="disabled"
            />
            <EscrButton
                color="primary"
                label="Export"
                :on-click="onSubmit"
                :disabled="disabled || invalid"
            />
        </template>
    </EscrModal>
</template>
<script>
import { mapActions, mapState } from "vuex";
import ArrayField from "../ArrayField/ArrayField.vue";
import DropdownField from "../Dropdown/DropdownField.vue";
import EscrButton from "../Button/Button.vue";
import EscrModal from "../Modal/Modal.vue";
import XIcon from "../Icons/XIcon/XIcon.vue";
import "../Common/Form.css";
import "./ExportModal.css";

export default {
    name: "EscrExportModal",
    components: {
        ArrayField,
        DropdownField,
        EscrButton,
        EscrModal,
        XIcon,
    },
    props: {
        /**
         * Boolean indicating whether or not the form fields should be disabled.
         */
        disabled: {
            type: Boolean,
            required: true,
        },
        /**
         * Whether or not the OpenITI Markdown export is enabled on the instance.
         */
        markdownEnabled: {
            type: Boolean,
            required: true,
        },
        /**
         * List of all region types on this document.
         */
        regionTypes: {
            type: Array,
            required: true,
        },
        /**
         * Whether or not the OpenITI TEI XML export is enabled on the instance.
         */
        teiEnabled: {
            type: Boolean,
            required: true,
        },
        /**
         * List of all transcription layers on this document.
         */
        transcriptions: {
            type: Array,
            required: true,
        },
        /**
         * Scope of the export task, which will appear in the header to indicate
         * whether you are exporting the entire document or specific images.
         */
        scope: {
            type: String,
            required: true,
        },
        /**
         * Callback function for submitting the export task.
         */
        onSubmit: {
            type: Function,
            required: true,
        },
        /**
         * Callback function for clicking "cancel".
         */
        onCancel: {
            type: Function,
            required: true,
        },
    },
    computed: {
        ...mapState({
            documentId: (state) => state.document.id,
            fileFormat: (state) => state.forms.export.fileFormat,
            formRegionTypes: (state) => state.forms.export.regionTypes,
            includeImages: (state) => state.forms.export.includeImages,
            includeCharacters: (state) => state.forms.export.includeCharacters,
            transcriptionLayer: (state) => state.forms.export.transcription,
        }),
        /**
         * this form is invalid and cannot be submitted if it is missing layer or file format
         */
        invalid() {
            return !this.transcriptionLayer || !this.fileFormat;
        },
        /**
         * collect region types options for checkbox elements
         */
        regionTypesOptions() {
            return this.regionTypes.map((type) => ({
                label: type.name,
                value: type.pk.toString(),
                selected: this.formRegionTypes.includes(type.pk.toString()),
            }));
        },
        /**
         * Convert transcription layers to options for select element
         */
        transcriptionOptions() {
            return this.transcriptions.map((transcription) => ({
                label: transcription.name,
                value: transcription.pk.toString(),
                selected: this.transcriptionLayer.toString() === transcription.pk.toString(),
            }));
        },
        /**
         * File format options for export
         */
        fileFormatOptions() {
            const formatOptions = [
                {
                    label: "Text",
                    value: "text",
                    selected: this.fileFormat === "text",
                },
                {
                    label: "PageXML",
                    value: "pagexml",
                    selected: this.fileFormat === "pagexml",
                },
                {
                    label: "ALTO",
                    value: "alto",
                    selected: this.fileFormat === "alto",
                },
            ];
            if (this.markdownEnabled) {
                formatOptions.push({
                    label: "OpenITI Markdown",
                    value: "openitimarkdown",
                    selected: this.fileFormat === "openitimarkdown",
                });
            }
            if (this.teiEnabled) {
                formatOptions.push({
                    label: "OpenITI TEI XML",
                    value: "teixml",
                    selected: this.fileFormat === "teixml",
                });
            }
            return formatOptions;
        },
    },
    created() {
        // initialize transcription field with user's last edited transcription
        // eslint-disable-next-line no-undef
        let itrans = userProfile.get("initialTranscriptions");
        if (itrans && itrans[this.documentId]) {
            this.handleGenericInput({
                form: "export",
                field: "transcription",
                value: itrans[this.documentId],
            });
        }
        // initialize export format with user's last selected format
        // eslint-disable-next-line no-undef
        let exportFormat = userProfile.get("exportFormat");
        if (exportFormat) {
            this.handleGenericInput({
                form: "export",
                field: "fileFormat",
                value: exportFormat,
            });
        }
    },
    methods: {
        ...mapActions("forms", [
            "handleCheckboxArrayInput",
            "handleGenericInput",
        ]),
        handleFileFormatChange(e) {
            this.handleGenericInput({
                form: "export", field: "fileFormat", value: e.target.value,
            });
            if (e.target.value === "text") {
                // if switching to text export, uncheck "include images"
                this.handleGenericInput({ form: "export", field: "includeImages", value: false });
            }
            // store the export format choice for later use
            // eslint-disable-next-line no-undef
            userProfile.set("exportFormat", e.target.value);
        },
        handleIncludeImagesChange(e) {
            this.handleGenericInput({
                form: "export",
                field: "includeImages",
                value: e.target.checked,
            });
        },
        handleIncludeCharactersChange(e) {
            this.handleGenericInput({
                form: "export",
                field: "includeCharacters",
                value: e.target.checked,
            });
        },
        handleRegionTypesChange(e) {
            this.handleCheckboxArrayInput({
                form: "export",
                field: "regionTypes",
                checked: e.target.checked,
                value: e.target.value,
            });
        },
        handleTranscriptionChange(e) {
            this.handleGenericInput({
                form: "export", field: "transcription", value: e.target.value,
            });
        },
    },
};
</script>
