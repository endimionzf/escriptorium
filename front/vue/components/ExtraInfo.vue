<template>
    <div>
        <div class="nav-div nav-item ml-2">
            <span
                v-if="$store.state.document.name"
                id="part-name"
            >{{ $store.state.document.name }}</span>
            <span
                v-if="$store.state.parts.loaded"
                id="part-title"
                title="Click to go to another Element (Alt+G)."
                data-toggle="modal"
                data-target="#gotoModal"
                role="button"
            >{{ $store.state.parts.title }} - {{ $store.state.parts.filename }} - ({{ imageSize }}) - {{ $store.state.parts.image_file_size | prettyBytes }}</span>
            <span
                v-if="!$store.state.parts.loaded"
                class="loading"
            >Loading&#8230;</span>
        </div>

        <div
            id="gotoModal"
            class="modal ui-draggable show"
            tabindex="-1"
            role="dialog"
        >
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div
                        class="modal-body"
                        style="line-height: 30px;"
                    >
                        Element #
                        <input
                            v-if="$store.state.parts.loaded"
                            id="goto-modal-input"
                            type="number"
                            min="1"
                            :max="$store.state.document.partsCount"
                            :value="$store.state.parts.order+1"
                            class="w-25"
                            @keyup.enter="goTo"
                        >
                        / {{ $store.state.document.partsCount }}
                        <button
                            class="btn btn-info float-right"
                            @click="goTo"
                        >
                            Go to
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    computed: {
        imageSize() {
            return this.$store.state.parts.image.size[0]+"x"+this.$store.state.parts.image.size[1];
        },
    },
    async created() {
        document.addEventListener("keyup", async function(event) {
            if (event.altKey && event.key.toLowerCase() == "g") {
                $("#gotoModal").modal("show");
            }
        });

        $(document).on("shown.bs.modal", "#gotoModal", function () {
            $("#goto-modal-input").focus();
        });
    },
    methods: {
        async goTo(ev) {
            let input = document.getElementById("goto-modal-input");
            if (input.value > 0 && input.value <= parseInt(input.attributes.max.value)) {
                await this.$store.dispatch("parts/loadPartByOrder", input.value-1);
                $("#gotoModal").modal("hide");
            }
        }
    }
}
</script>

<style scoped>
</style>
