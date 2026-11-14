/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ZenCoreFieldRoleEntry extends Component {
    static template = xml`<div class="o_zc_role_entry p-4" role="status">Opening ZenCore Field…</div>`;
    static props = ["*"];
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        onMounted(() => { void this.routeToLanding(); });
    }
    async routeToLanding() {
        try {
            // Odoo 19 does not provide a `user` service in every webclient.
            // Resolve the authorized landing action on the server instead.
            const landingAction = await this.orm.call(
                "res.users", "zc_get_field_landing_action", []
            );
            await this.actionService.doAction(
                landingAction,
                { clearBreadcrumbs: true }
            );
        } catch (error) {
            console.error("ZenCore Field landing page failed", error);
            // The app stays in Odoo with an actionable error instead of a redirect loop.
            const target = document.querySelector(".o_zc_role_entry");
            if (target) target.textContent = "Unable to open the default page. Select Visit Plans from the menu.";
        }
    }
}
registry.category("actions").add("zencore_field_role_entry", ZenCoreFieldRoleEntry);
