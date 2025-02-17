<template>
    <div>
        <table
            v-if="types"
            class="escr-table annotation-ontology"
        >
            <thead>
                <tr>
                    <th class="name-column">
                        <div><span>Name</span></div>
                    </th>
                    <th>
                        <div><span>Button Text</span></div>
                    </th>
                    <th>
                        <div><span>Components</span></div>
                    </th>
                    <th>
                        <div><span>Type</span></div>
                    </th>
                    <th>
                        <div><span>Marker Type</span></div>
                    </th>
                    <th class="color-column">
                        <div><span>Color</span></div>
                    </th>
                    <th class="comments-column">
                        <div><span>Comments</span></div>
                    </th>
                    <th class="remove-column" />
                </tr>
            </thead>
            <tbody>
                <tr
                    v-for="item, idx in types"
                    :key="item.pk"
                >
                    <!-- name -->
                    <td class="name-column escr-text-field">
                        <input
                            type="text"
                            :disabled="disabled"
                            :value="item.name"
                            :invalid="!item.name"
                            @input="(e) => onChange(e, 'name', item)"
                        >
                    </td>
                    <!-- abbreviation -->
                    <td class="abbreviation-column escr-text-field">
                        <input
                            type="text"
                            maxlength="3"
                            :disabled="disabled"
                            :value="item.abbreviation"
                            :invalid="!item.abbreviation"
                            @input="(e) => onChange(e, 'abbreviation', item)"
                        >
                    </td>
                    <!-- component selection -->
                    <td>
                        <VMenu
                            placement="bottom-end"
                            theme="modal-menu"
                            :distance="8"
                            :shown="componentDropdownOpen === idx"
                            :triggers="[]"
                            :auto-hide="true"
                            @apply-hide="() => closeComponentDropdown(idx)"
                        >
                            <EscrButton
                                :on-click="() => openComponentDropdown(idx)"
                                :class="{
                                    ['escr-component-dropdown']: true,
                                    placeholder: !(item.components && item.components.length)
                                }"
                                size="small"
                                color="text"
                                :label="(item.components && item.components.length)
                                    ? `${item.components.length} selected`
                                    : 'Components'"
                            >
                                <template #button-icon-right>
                                    <ChevronDownIcon />
                                </template>
                            </EscrButton>
                            <template #popper>
                                <div class="escr-component-selector">
                                    <ul v-if="components && components.length">
                                        <li
                                            v-for="component in components"
                                            :key="component.pk"
                                        >
                                            <label>
                                                <input
                                                    type="checkbox"
                                                    :checked="item.components &&
                                                        item.components.some((comp) =>
                                                            comp.pk === parseInt(component.pk)
                                                        )"
                                                    @change="() => toggleComponent(item, component)"
                                                >
                                                <span>{{ component.name }}</span>
                                            </label>
                                            <EscrButton
                                                size="small"
                                                color="text"
                                                :on-click="() => openEditComponentModal(component)"
                                            >
                                                <template #button-icon>
                                                    <PencilIcon />
                                                </template>
                                            </EscrButton>
                                            <EscrButton
                                                size="small"
                                                color="text"
                                                :on-click="() => openConfirmDeleteComponent(
                                                    component
                                                )"
                                            >
                                                <template #button-icon>
                                                    <XIcon />
                                                </template>
                                            </EscrButton>
                                        </li>
                                    </ul>
                                    <div
                                        v-else
                                        class="escr-no-components"
                                    >
                                        <span>No Components</span>
                                        <small>Click "Add New" to add</small>
                                    </div>
                                </div>
                                <div>
                                    <EscrButton
                                        size="small"
                                        color="text"
                                        label="Add New"
                                        :on-click="openAddComponentModal"
                                    >
                                        <template #button-icon>
                                            <PlusIcon />
                                        </template>
                                    </EscrButton>
                                </div>
                            </template>
                        </VMenu>
                    </td>
                    <!-- type -->
                    <td class="escr-text-field">
                        <input
                            type="text"
                            :disabled="disabled"
                            :value="(item.typology && item.typology.name) || ''"
                            @input="(e) => onChange(e, 'typology.name', item)"
                        >
                    </td>
                    <!-- marker type -->
                    <td>
                        <DropdownField
                            label="Marker type"
                            :disabled="disabled"
                            :options="getMarkerTypeOptions(item)"
                            :on-change="(e) => onChange(e, 'marker_type', item)"
                            :label-visible="false"
                        />
                    </td>
                    <!-- marker color -->
                    <td
                        class="color-column"
                    >
                        <input
                            type="color"
                            class="escr-color-button"
                            aria-label="select color"
                            :disabled="disabled"
                            :value="item.marker_detail"
                            @focusout="(e) => onChange(e, 'marker_detail', item)"
                        >
                    </td>
                    <!-- delete -->
                    <td class="comments-column">
                        <label
                            class="comments-toggle"
                            :disabled="disabled"
                        >
                            <input
                                type="checkbox"
                                class="sr-only"
                                :disabled="disabled"
                                :checked="item.has_comments"
                                @change="(e) => onToggleComments(e, item)"
                            >
                            <ToggleOnIcon v-if="item.has_comments" />
                            <ToggleOffIcon v-else />
                        </label>
                    </td>
                    <!-- delete -->
                    <td class="remove-column">
                        <EscrButton
                            size="small"
                            color="text"
                            :disabled="disabled"
                            :on-click="() => onRemoveType(item)"
                        >
                            <template #button-icon>
                                <XIcon />
                            </template>
                        </EscrButton>
                    </td>
                </tr>
            </tbody>
        </table>
        <EscrModal
            v-if="addComponentModalOpen"
            class="escr-add-component"
        >
            <template #modal-header>
                <h2>{{ editComponentMode === 'add' ? "Add New" : "Edit" }} Component</h2>
                <EscrButton
                    color="text"
                    :on-click="closeAddComponentModal"
                    size="small"
                >
                    <template #button-icon>
                        <XIcon />
                    </template>
                </EscrButton>
            </template>
            <template #modal-content>
                <TextField
                    label="Name"
                    placeholder="Name"
                    :disabled="disabled"
                    :on-input="(e) => handleGenericInput({
                        form: 'addComponent', field: 'name', value: e.target.value
                    })"
                    :value="addComponentForm.name"
                    :invalid="componentFormInvalid"
                    required
                />
                <TextField
                    help-text="Comma-separated list of accepted values for this component"
                    label="Allowed Values"
                    placeholder="Allowed Values"
                    :disabled="disabled"
                    :on-input="(e) => handleGenericInput({
                        form: 'addComponent', field: 'values', value: e.target.value
                    })"
                    :value="addComponentForm.values"
                />
            </template>
            <template #modal-actions>
                <EscrButton
                    color="outline-primary"
                    label="Cancel"
                    :disabled="disabled"
                    :on-click="closeAddComponentModal"
                />
                <EscrButton
                    color="primary"
                    :label="editComponentMode === 'add' ? 'Add' : 'Save'"
                    :disabled="disabled"
                    :on-click="editComponentMode === 'add' ? onAddComponent : onUpdateComponent"
                />
            </template>
        </EscrModal>
        <ConfirmModal
            v-if="confirmDeleteComponentModalOpen"
            :body-text="`Are you sure you want to delete ${componentToDelete.name}?`"
            confirm-verb="Delete"
            title="Delete Component"
            :cannot-undo="true"
            :disabled="disabled"
            :on-cancel="closeConfirmDeleteComponent"
            :on-confirm="onDeleteComponent"
        />
    </div>
</template>
<script>
import { Menu as VMenu } from "floating-vue";
import { mapActions, mapState } from "vuex";
import ChevronDownIcon from "../Icons/ChevronDownIcon/ChevronDownIcon.vue";
import ConfirmModal from "../ConfirmModal/ConfirmModal.vue";
import DropdownField from "../Dropdown/DropdownField.vue";
import EscrButton from "../Button/Button.vue";
import EscrModal from "../Modal/Modal.vue";
import PencilIcon from "../Icons/PencilIcon/PencilIcon.vue";
import PlusIcon from "../Icons/PlusIcon/PlusIcon.vue";
import TextField from "../TextField/TextField.vue";
import ToggleOffIcon from "../Icons/ToggleOffIcon/ToggleOffIcon.vue";
import ToggleOnIcon from "../Icons/ToggleOnIcon/ToggleOnIcon.vue";
import XIcon from "../Icons/XIcon/XIcon.vue";
import "./AnnotationOntologyTable.css";

export default {
    name: "AnnotationOntologyTable",
    components: {
        ChevronDownIcon,
        ConfirmModal,
        DropdownField,
        EscrButton,
        EscrModal,
        PencilIcon,
        PlusIcon,
        TextField,
        ToggleOffIcon,
        ToggleOnIcon,
        VMenu,
        XIcon,
    },
    props: {
        /**
         * True if all buttons and form fields should be disabled
         */
        disabled: {
            type: Boolean,
            required: true,
        },
        /**
         * Callback for removing an item
         */
        onRemoveType: {
            type: Function,
            required: true,
        },
        /**
         * Current tab (i.e. whether these are image or text annotations)
         */
        tab: {
            type: String,
            required: true,
        },
        /**
         * All annotation types (from the form state)
         */
        types: {
            type: Array,
            required: true,
        },
    },
    data() {
        return {
            addComponentModalOpen: false,
            componentDropdownOpen: null,
            componentFormInvalid: false,
            componentToDelete: null,
            confirmDeleteComponentModalOpen: false,
            editComponentMode: "",
        };
    },
    computed: {
        ...mapState({
            addComponentForm: (state) => state.forms.addComponent,
            components: (state) => state.document.componentTaxonomies,
        }),
    },
    methods: {
        ...mapActions("document", ["createComponent", "deleteComponent", "updateComponent"]),
        ...mapActions("forms", ["clearForm", "handleGenericInput", "handleGenericArrayInput"]),
        /**
         * Close the "add new component" modal and clear its state
         */
        closeAddComponentModal() {
            this.addComponentModalOpen = false;
            this.componentFormInvalid = false;
            this.editComponentMode = "";
            this.clearForm("addComponent");
        },
        /**
         * Close the component selector dropdown
         */
        closeComponentDropdown(idx) {
            if (this.componentDropdownOpen === idx) {
                this.componentDropdownOpen = null;
            }
        },
        /**
         * Populate the marker type dropdown, including which element is selected, for an item
         */
        getMarkerTypeOptions(item) {
            if (this.tab === "text") {
                return [
                    {
                        label: "Background Color",
                        value: "Background Color",
                        selected: item.marker_type === "Background Color",
                    },
                    {
                        label: "Text Color",
                        value: "Text Color",
                        selected: item.marker_type === "Text Color",
                    },
                    { label: "Bold", value: "Bold", selected: item.marker_type === "Bold" },
                    { label: "Italic", value: "Italic", selected: item.marker_type === "Italic" },
                ];
            } else if (this.tab === "image") {
                return [
                    {
                        label: "Rectangle",
                        value: "Rectangle",
                        selected: item.marker_type === "Rectangle"
                    },
                    {
                        label: "Polygon", value: "Polygon", selected: item.marker_type === "Polygon"
                    },
                ];
            }
            return [];
        },
        /**
         * Callback to create a new component
         */
        async onAddComponent() {
            if (this.addComponentForm.name) {
                this.componentFormInvalid = false;
                await this.createComponent();
                this.closeAddComponentModal();
            } else {
                this.componentFormInvalid = true;
            }
        },
        /**
         * Callback to save changes to a component
         */
        async onUpdateComponent() {
            if (this.addComponentForm.name) {
                this.componentFormInvalid = false;
                await this.updateComponent();
                this.closeAddComponentModal();
            } else {
                this.componentFormInvalid = true;
            }
        },
        /**
         * Generic form fields event handler
         */
        onChange(e, field, item) {
            const value = structuredClone(item);
            if (field === "typology.name") {
                value["typology"] = { name: e.target.value };
            } else {
                value[field] = e.target.value;
            }
            this.handleGenericArrayInput({
                form: "ontology", field: this.tab, action: "update", value
            });
        },
        /**
         * Handler for toggling comments on and off for an item
         */
        onToggleComments(e, item) {
            const value = structuredClone(item);
            value["has_comments"] = e.target.checked;
            this.handleGenericArrayInput({
                form: "ontology", field: this.tab, action: "update", value
            });
        },
        /**
         * Open the component selector dropdown for a specific item
         */
        openComponentDropdown(idx) {
            this.componentDropdownOpen = idx;
        },
        /**
         * Open the "add new component" modal
         */
        openAddComponentModal() {
            this.componentDropdownOpen = null;
            this.addComponentModalOpen = true;
            this.editComponentMode = "add";
        },
        /**
         * Open the "edit component" modal
         */
        openEditComponentModal(component) {
            // set the form values to the existing values from db
            this.handleGenericInput({
                form: "addComponent", field: "name", value: component.name
            });
            this.handleGenericInput({
                form: "addComponent", field: "values", value: component.allowed_values.join(",")
            });
            this.handleGenericInput({
                form: "addComponent", field: "pk", value: component.pk
            });
            // then open the modal and set the mode to edit mode
            this.componentDropdownOpen = null;
            this.addComponentModalOpen = true;
            this.editComponentMode = "edit";
        },
        /**
         * Open a modal to confirm deletion of an annotation component
         */
        openConfirmDeleteComponent(component) {
            this.componentToDelete = component;
            this.componentDropdownOpen = null;
            this.confirmDeleteComponentModalOpen = true;
        },
        /**
         * Close the modal to confirm deletion of an annotation component
         */
        closeConfirmDeleteComponent() {
            this.componentToDelete = null;
            this.confirmDeleteComponentModalOpen = false;
        },
        /**
         * Open a modal to confirm deletion of an annotation component
         */
        async onDeleteComponent() {
            await this.deleteComponent(this.componentToDelete);
            this.closeConfirmDeleteComponent();
        },
        /**
         * Handler for toggling a component choice on and off for an item
         */
        toggleComponent(item, component) {
            const value = structuredClone(item);
            const componentIndex = value.components.findIndex((c) => c.pk === component.pk)
            if (componentIndex === -1) {
                value.components.push(component);
            } else {
                value.components.splice(componentIndex, 1);
            }
            this.handleGenericArrayInput({
                form: "ontology", field: this.tab, action: "update", value
            });
        }
    }
}
</script>
