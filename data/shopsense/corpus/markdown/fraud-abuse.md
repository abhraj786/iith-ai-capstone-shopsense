# Return Fraud and Abuse Prevention Standard

# KARTWAY CUSTOMER OPERATIONS POLICY HANDBOOK
**Document Reference:** COP-POL-0442
**Section:** Post-Order Resolutions and Risk Controls
**Standard:** Return and Refund Abuse Policy
**Effective Date:** October 1, 2024
**Policy Owner:** Director of Risk and Trust (H. Vance)

---

### 1.0 PURPOSE AND SCOPE
1.1 This standard establishes the operational requirements for identifying, restricting, and managing buyer accounts exhibiting patterns of return and refund abuse across the Kartway marketplace.
1.2 This policy binds all tier-1 frontline support representatives, tier-2 resolution specialists, automated service assistants, and fraud operations personnel.

---

### 2.0 RETURN-RATE THRESHOLDS FOR SYSTEM REVIEW
2.1 **System-Calculated Return Rate:** The platform risk monitor continuously computes an account’s lifetime return rate as:
$$\text{Return Rate} = \frac{\text{Total Completed Returns}}{\text{Total Lifetime Completed Orders}}$$
2.2 **Review Threshold:** An account shall automatically be placed into review status when both of the following conditions are met:
* 2.2.1 The account has accumulated a minimum of 10 lifetime completed orders; and
* 2.2.2 The account has a return rate equal to or greater than 0.40 (40% of orders returned).
2.3 **Review Outcomes:** Following an automated trigger under clause 2.2, the Risk Operations Desk must evaluate the account history and assign one of two discrete outcomes:
* 2.3.1 **Cleared:** The return activity is determined to be legitimate (e.g., verified platform errors, catalog discrepancies), returning the account to standard status.
* 2.3.2 **Flagged:** The return pattern is determined to be abusive or non-viable, maintaining permanent restrictions under Section 4.0.
2.4 **Discretionary Flagging:** The Kartway Fraud Team maintains authority to flag any account based on independent evidence of abuse, collusion, or misrepresentation, regardless of whether the account has reached 10 lifetime orders or a 0.40 return rate.

---

### 3.0 SERIAL REFUND REQUESTERS
3.1 **Definition:** A buyer who submits three (3) or more refund requests within any rolling ninety (90) calendar-day window is classified as a "Serial Refund Requester."
3.2 **Automatic Status Transition:** The submission of the third refund request within the 90-day window automatically places the account into active review status.
3.3 **Scope of Requests:** The 90-day calculation includes all refund requests submitted across all order types, categories, and fulfillment models, regardless of whether the requests were initiated via self-service tools, agent interaction, or merchant mediation.

---

### 4.0 TRANSACTION RESTRICTIONS AND ROUTING
4.1 **Suspension of Automated Approvals:** While an account maintains a status of "Under Review" or "Flagged":
* 4.1.1 Frontline agents and automated systems are strictly prohibited from issuing automated, instant, or concessionary approvals for any refund, return authorization, or item replacement.
* 4.1.2 This prohibition applies universally, regardless of the item category, merchant agreement, or transaction monetary amount (including low-value orders otherwise eligible for zero-touch resolution under standard rules).
4.2 **Routing Tag:** Any incoming refund, return, or replacement request originating from an account that is flagged or under review must be assigned the ticket category tag `account_under_review` and routed immediately to the Fraud Desk queue.
4.3 **Resolution Authority:** Only assigned analysts within the Fraud Operations Unit hold authorization to approve, reject, or conditionally process requests routed under the `account_under_review` tag.

---

### 5.0 CUSTOMER COMMUNICATIONS AND DISCLOSURE PROHIBITION
5.1 **Strict Non-Disclosure:** Support agents, automated bots, and messaging assistants must never confirm, deny, or imply to a customer that their account has been flagged, placed under review, or referred to risk mitigation teams.
5.2 **Approved Messaging:** When an incoming refund, return, or replacement request cannot be processed immediately due to an account status restriction, personnel must deploy only approved neutral scripting:
* *Script Template S-102:* "Your request requires standard administrative review by our processing department. We have routed your case to a specialist, who will follow up via your registered email address within our standard processing timeline."
5.3 **Violation:** Disclosing internal risk tags, return-rate percentages, fraud scores, or the existence of the `account_under_review` queue to an end customer constitutes a breach of protocol and is subject to immediate disciplinary escalation under HR Code 11-B.

---

### 6.0 ESCALATION ROUTE FOR SUSPECTED FRAUD
6.1 **Frontline Escalations:** If a frontline agent handles an account that does not meet the automated return-rate threshold (clause 2.2) or serial requester criteria (clause 3.1), but presents physical or documentary evidence of fraud (such as altered shipping labels, empty box claims, or abusive chargeback threats), the agent must not process the resolution.
6.2 **Queue Escalation:** The agent must tag the active ticket as `account_under_review`, append internal notes detailing the specific evidentiary anomalies, and reassign the ticket directly to Fraud Operations via Desk Route: `RiskOps-Escalations-L2`.
