# ZenCore Field V30 — Registration & Password Reset (Odoo 19)

## Scope
- Mobile `Profile` when signed out: `Sign In to Odoo`, `Request New Account`, and `Forgot Password?`.
- Account request collects **Full Name, Email, Phone, Requested Role**. No password is collected before approval. Password setup and confirmation occur on Odoo's own email-linked invitation page, not in the app. This is an intentional security change to the initial preview.
- Requests are not users. Only an authorized CEO/Manager (or system administrator) can approve; CEO role assignment is reserved for system administrators, Manager role to CEO/admin. Reports To hierarchy must be valid.
- Public endpoint does not disclose whether an account exists. Its generic response is not confirmation of user creation.
- Existing login, GPS SQLite, auto-sync, camera queue, mobile maps, visit plans and historical tracking are left unchanged.

## Odoo.sh staging setup
1. Take a backup of the staging database. Upgrade `zencore_salesperson_tracking` to the compatible V29 version, then upgrade `zencore_field_mobile_bridge` to **19.0.14.0.0**.
2. Ensure `auth_signup` is installed (declared as Bridge dependency).
3. Configure an outgoing SMTP server. In Odoo Settings, verify password reset emails and the publicly reachable HTTPS `web.base.url`.
4. As **System Administrator**, turn on registration explicitly under **Settings > Technical > Parameters > System Parameters**:
   - Key: `zencore_field_mobile_bridge.registration_enabled`
   - Value: `True`
   Keep it disabled (`False`) when not accepting account requests. It is **OFF by default**.
5. Use the **exact database technical name** from Odoo.sh in Mobile Profile > Database. The backend rejects submissions for a different database name.
6. CEO/Manager can review requests in **Salesperson Tracking > Mobile Account Requests**. This action is not visible to Supervisor or Salesperson.

## Registration test
1. Sign out in the mobile Profile, without uninstalling or clearing local data.
2. Tap `Request New Account`. Enter the staging Odoo root URL, actual DB name, full name, email, phone and requested role. Submit.
3. Mobile displays a generic acknowledgment. A non-existing email creates a **Pending** request; an existing email is not disclosed.
4. As Manager, open the new pending request. Choose `Assigned Role` (the requester cannot self-assign privileges), choose the appropriate Reports To person, then `Approve & Invite`.
5. Verify Odoo creates an internal user, synchronizes field security groups, and sends an Odoo password-set invitation. Open the email, set and confirm the password **on Odoo**, then sign in to mobile.
6. Repeat registration with an existing email and verify the mobile response does not reveal account existence.
7. Confirm a Manager cannot approve Manager/CEO roles and only System Administrator can grant CEO.
8. Confirm the registration endpoint is disabled until the System Parameter is explicitly enabled.
9. Confirm a Supervisor/Salesperson cannot see the request menu or approve via ORM RPC.

## Forgot password test
1. Sign out and tap `Forgot Password?`.
2. Enter the trusted HTTPS root URL, then `Open Odoo Password Reset`.
3. Enter the email address on Odoo's own reset form and follow the mailed secure link. The app never receives the password or reset token.
4. If Odoo has password reset disabled or SMTP is not configured, ask the administrator to enable/reset it in Odoo. The app cannot bypass the server policy.

## Limitations and security notes
- There is deliberately **no public "email exists / email not found" lookup**; exposing it invites account enumeration.
- Approval requires a valid reporting superior (Salesperson -> Supervisor -> Manager -> CEO); configure the hierarchy first.
- Generic success responses cannot guarantee email delivery or account existence.
- The public registration API applies basic hourly IP and daily email throttles, but high-traffic production systems should add reverse-proxy/WAF rate limiting, CAPTCHA or verified email ownership before accepting untrusted registrations.
- Static tests are not an Odoo.sh registry upgrade or a real Android/SMTP test.
