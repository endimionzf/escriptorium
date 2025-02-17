<template>
    <div
        :class="classes"
        aria-live="assertive"
        role="alert"
    >
        <span>
            {{ message }}{{ count > 1 ? ` (${count})` : "" }}
        </span>
        <a
            v-if="actionLink && actionLabel"
            :href="actionLink"
            target="_blank"
            rel="noopener noreferrer"
            class="escr-button escr-button--small escr-button--outline-text"
        >
            {{ actionLabel }}
        </a>
        <EscrButton
            v-else-if="actionFn && actionLabel"
            :label="actionLabel"
            :on-click="actionFn"
            color="outline-text"
            size="small"
        />
        <EscrButton
            :on-click="onClose"
            aria-label="Close"
            color="text"
            size="small"
        >
            <template #button-icon>
                <XIcon />
            </template>
        </EscrButton>
    </div>
</template>
<script>
import EscrButton from "../Button/Button.vue";
import XIcon from "../Icons/XIcon/XIcon.vue";
import "./Toast.css";

export default {
    name: "EscrToast",
    components: { EscrButton, XIcon },
    props: {
        /**
         * Optional function to pass to an action button on the alert.
         */
        actionFn: {
            type: Function,
            default: null,
        },
        /**
         * Optional label to display on an action button on the alert.
         */
        actionLabel: {
            type: String,
            default: "",
        },
        /**
         * Optional link to pass to an action button on the alert.
         */
        actionLink: {
            type: String,
            default: "",
        },
        /**
         * The color of the toast alert, which must be one of `alert`, `success`, or `test`.
         */
        color: {
            type: String,
            default: "text",
            validator(value) {
                return [
                    "alert",
                    "success",
                    "text",
                ].includes(value);
            },
        },
        /**
         * If there is more than one alert with the same message, this count can be appended
         * to the message string in order to group them into a single toast.
         */
        count: {
            type: Number,
            default: 1,
        },
        /**
         * By default, toasts will disappear after 2000 ms (2 seconds). Provide a number
         * here to change the delay, or pass 0 to disable auto-disappearance.
         */
        delay: {
            type: Number,
            default: 2000,
        },
        /**
         * The message to display for the toast alert.
         */
        message: {
            type: String,
            required: true,
        },
        /**
         * Callback that is called after `delay` ms, or by clicking the close button.
         */
        onClose: {
            type: Function,
            required: true,
        },
    },
    computed: {
        classes() {
            return {
                "escr-toast": true,
                [`escr-toast--${this.color}`]: true,
            };
        }
    },
    watch: {
        count() {
            if (this.delay) {
                setTimeout(this.onClose, this.delay);
            }
        },
    },
    mounted() {
        if (this.delay) {
            setTimeout(this.onClose, this.delay);
        }
    },
}
</script>
