import { Component, onMounted, onWillDestroy, useState, xml } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

export class PerformancePdfPreview extends Component {
    static components = { Dialog };
    static props = { reportUrl: String, filename: String, title: { type: String, optional: true }, close: Function };
    static template = xml`
        <Dialog title="title" size="'fullscreen'" footer="false" withBodyPadding="false">
            <div class="d-flex flex-column" style="height: calc(100dvh - 110px); min-height: 320px;">
                <div class="d-flex flex-wrap align-items-center gap-2 border-bottom p-2 bg-light">
                    <span class="text-muted me-auto">Use the PDF viewer toolbar to print the displayed document.</span>
                    <button type="button" class="btn btn-outline-secondary" t-on-click="download" t-att-disabled="!state.pdfUrl">
                        <i class="fa fa-download me-1"/> Download PDF
                    </button>
                    <button type="button" class="btn btn-secondary" t-on-click="props.close">Close</button>
                </div>
                <div t-if="state.loading" class="d-flex flex-grow-1 align-items-center justify-content-center" role="status">
                    <i class="fa fa-spinner fa-spin me-2"/> Generating PDF preview…
                </div>
                <div t-elif="state.error" class="alert alert-danger m-3" role="alert" t-esc="state.error"/>
                <iframe t-elif="state.viewerUrl" t-att-src="state.viewerUrl" class="w-100 flex-grow-1 border-0" style="min-height: 0;" t-att-title="title" t-on-load="prepareViewer"/>
            </div>
        </Dialog>`;

    setup() {
        this.title = this.props.title || _t("PDF Preview – Salesperson Performance Report");
        this.state = useState({ loading: true, error: "", pdfUrl: "", viewerUrl: "" });
        this.abortController = new AbortController();
        this.destroyed = false;
        this.pdfUrl = null;
        onMounted(() => { void this.loadPdf(); });
        onWillDestroy(() => {
            this.destroyed = true;
            this.abortController.abort();
            if (this.pdfUrl) {
                URL.revokeObjectURL(this.pdfUrl);
            }
        });
    }

    async loadPdf() {
        try {
            const url = new URL(this.props.reportUrl, window.location.origin);
            const allowedReportUrl = /^\/report\/pdf\/zencore_salesperson_tracking\.report_(salesperson_performance|customer_detailed)_document\/\d+$/;
            if (url.origin !== window.location.origin || !allowedReportUrl.test(url.pathname)) {
                throw new Error("Invalid report URL");
            }
            url.searchParams.set("context", JSON.stringify(user.context));
            const response = await fetch(url, { credentials: "same-origin", cache: "no-store", signal: this.abortController.signal });
            if (!response.ok || !response.headers.get("Content-Type")?.toLowerCase().includes("application/pdf")) {
                throw new Error("PDF response unavailable");
            }
            const pdf = await response.blob();
            if (!pdf.size || await pdf.slice(0, 5).text() !== "%PDF-") {
                throw new Error("Invalid PDF response");
            }
            if (this.destroyed) {
                return;
            }
            this.pdfUrl = URL.createObjectURL(pdf);
            this.state.pdfUrl = this.pdfUrl;
            this.state.viewerUrl = `/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent(this.pdfUrl)}#zoom=page-width`;
        } catch (error) {
            if (!this.destroyed && error.name !== "AbortError") {
                this.state.error = _t("Unable to generate the PDF preview. Check your access rights and PDF rendering configuration, then reopen the report.");
            }
        } finally {
            if (!this.destroyed) {
                this.state.loading = false;
            }
        }
    }

    prepareViewer(event) {
        const doc = event.currentTarget.contentDocument;
        if (doc?.head) {
            const style = doc.createElement("style");
            style.textContent = "#editorModeButtons, #editorModeSeparator, #openFile, #secondaryOpenFile, #viewBookmark, #viewBookmarkSeparator { display: none !important; }";
            doc.head.appendChild(style);
        }
    }

    download() {
        if (!this.pdfUrl) {
            return;
        }
        const link = document.createElement("a");
        link.href = this.pdfUrl;
        link.download = this.props.filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
    }
}

registry.category("actions").add("zencore_performance_pdf_preview", (env, action) => {
    env.services.dialog.add(PerformancePdfPreview, {
        reportUrl: action.params.report_url,
        filename: action.params.filename,
        title: _t("PDF Preview – Salesperson Performance Report"),
    });
});

registry.category("actions").add("zencore_customer_pdf_preview", (env, action) => {
    env.services.dialog.add(PerformancePdfPreview, {
        reportUrl: action.params.report_url,
        filename: action.params.filename,
        title: _t("PDF Preview – Customer Visit Report"),
    });
});
