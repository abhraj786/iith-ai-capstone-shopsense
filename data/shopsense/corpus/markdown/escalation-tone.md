# Escalation Triggers and Customer Communication Standard

# KARTWAY CUSTOMER OPERATIONS POLICY HANDBOOK
**Document ID:** COP-STD-0419
**Effective Date:** 01 November 2024
**Owner:** Director of Customer Experience (CX Operations)
**Applies To:** Automated Routing Engine (KartBot), Frontline Tier-1 Support Agents, Operations Supervisors

---

### 1.0 PURPOSE AND APPLICATION
1.1. This standard specifies the mandatory conditions under which an automated support interaction on the Kartway platform must immediately terminate automated handling and transfer the customer to a designated human queue.
1.2. Automated systems and frontline support routing logic must evaluate all active conversational sessions against the triggers defined in Section 2.0. No exceptions or bypasses to these routing directives are permitted without signed authorization from the Operations Duty Manager.

---

### 2.0 MANDATORY HUMAN ESCALATION TRIGGERS
Every automated workflow and support routing pipeline must evaluate inbound sessions for the following eight (8) triggers and route tickets exclusively to the target teams specified. No additional escalation triggers may be defined in automated routing tables.

#### 2.1. Trigger Code: `human_requested`
*   **Definition:** The customer explicitly states via keyword, phrase, or menu selection that they wish to communicate with a human representative (e.g., "speak to a person", "human agent", "real person", "operator").
*   **Target Queue / Team:** `agent`
*   **Transfer SLA:** The interaction must be routed and enqueued for the `agent` queue within 45 seconds of input recognition.

#### 2.2. Trigger Code: `angry_or_abusive`
*   **Definition:** The customer uses profanity, derogatory language, personal insults toward staff, discriminatory remarks, or communicates in a tone identified by sentiment scoring as unambiguously enraged or aggressive.
*   **Target Queue / Team:** `team_lead`
*   **Transfer SLA:** Automated deflection must cease immediately; transfer to `team_lead` must occur within 30 seconds.

#### 2.3. Trigger Code: `repeat_contact`
*   **Definition:** Third or later inbound contact regarding the same Order Reference Number (ORN). Specifically, this trigger fires when the Kartway CRM records that the customer has already submitted two (2) or more distinct prior inquiries (tickets, chats, or calls) associated with that specific ORN, regardless of prior resolution status.
*   **Target Queue / Team:** `team_lead`
*   **Transfer SLA:** Instantaneous queue assignment to `team_lead` upon validation of the ORN contact counter ($\ge 2$ prior logged contacts).

#### 2.4. Trigger Code: `legal_or_regulatory`
*   **Definition:** The customer explicitly mentions retainment of legal counsel, filing a formal legal claim, approaching a consumer disputes forum (e.g., District Consumer Disputes Redressal Commission), contacting state or national commerce authorities, or filing a grievance with statutory ombudsmen.
*   **Target Queue / Team:** `legal_desk`
*   **Transfer SLA:** Direct queue assignment to `legal_desk` within 15 seconds. Automated responses must cease entirely.

#### 2.5. Trigger Code: `product_safety`
*   **Definition:** The customer asserts that a purchased item resulted in, or poses a direct risk of, bodily injury, illness, burns, smoke emission, electrical shock, spontaneous overheating, chemical exposure, or structural fire.
*   **Target Queue / Team:** `safety_desk`
*   **Transfer SLA:** Ticket flagged with Priority 1 Critical and placed into the `safety_desk` queue within 15 seconds.

#### 2.6. Trigger Code: `refund_above_auto_cap`
*   **Definition:** A requested refund, return-to-refund, or replacement item value exceeds the threshold of exactly 2,000 Indian Rupees (INR 2,000.00).
*   **Target Queue / Team:** `refund_approver`
*   **Transfer SLA:** The workflow must lock automated disbursement and route the authorization request packet to `refund_approver` within 60 seconds.

#### 2.7. Trigger Code: `account_under_review`
*   **Definition:** A refund, return, or replacement request originating from an account marked with the internal risk flag `STATUS_ABUSE_REVIEW`, indicating prior abusive return behavior, concession exploitation, or suspicious cross-account activity.
*   **Target Queue / Team:** `fraud_desk`
*   **Transfer SLA:** Automated processing must be suspended; the session must transfer directly to `fraud_desk` within 30 seconds without disclosing the risk flag to the customer.

#### 2.8. Trigger Code: `delivery_dispute`
*   **Definition:** The logistics partner's Last-Mile Carrier API returns a status of `DELIVERED`, but the customer asserts the parcel was not received, is missing, or was handed to an unauthorized party.
*   **Target Queue / Team:** `agent`
*   **Transfer SLA:** Queue assignment to `agent` within 60 seconds to initiate proof-of-delivery (POD) retrieval workflows.

---

### 3.0 OPERATIONAL ROUTING & THRESHOLD RULES

```
[Customer Interaction]
         │
         ├──> ORN Prior Contacts ≥ 2? ──────────────> [team_lead] (repeat_contact)
         ├──> Customer Explicit Human Request? ─────> [agent] (human_requested)
         ├──> Profanity / Overt Anger Detected? ────> [team_lead] (angry_or_abusive)
         ├──> Mention of Law / Forum / Regulator? ──> [legal_desk] (legal_or_regulatory)
         ├──> Smoke / Fire / Injury / Hazards? ─────> [safety_desk] (product_safety)
         ├──> Refund / Replacement > ₹2,000? ───────> [refund_approver] (refund_above_auto_cap)
         ├──> Account Marked Return Abuse? ─────────> [fraud_desk] (account_under_review)
         └──> Tracking = Delivered & User Denies? ──> [agent] (delivery_dispute)
```

3.1. **Strict Counting for `repeat_contact`:**
* The customer operations database checks the primary Order Reference Number (ORN).
* If `InboundContactCount(ORN) >= 2`, the current session constitutes the 3rd (or greater) contact. The system must immediately trigger `repeat_contact` and redirect the ticket to `team_lead`. Previous contacts include closed tickets, dropped calls, and completed chat sessions occurring within 30 calendar days of order placement.

3.2. **Value Evaluation for `refund_above_auto_cap`:**
* The threshold applies to the aggregate value of the line item(s) being refunded or replaced in the specific session.
* Values equal to or below INR 2,000.00 remain eligible for automated deflection or tier-1 resolution. Any value equal to INR 2,000.01 or greater triggers `refund_above_auto_cap`.

---

### 4.0 COMMUNICATION TONE AND LIABILITY RESTRICTIONS

4.1. **Required Tone Guidance:**
All pre-routing messaging generated by the Kartway automated assistant must adhere to the following communication guidelines:
*   Maintain a calm, objective, polite, and professional register at all times.
*   Acknowledge delays or points of contact plainly without emotional escalation or hyperbole.
*   Do not mimic human personas; the assistant must identify itself as the "Kartway Automated Support Assistant" if asked.
*   Provide clear transfer notices to the customer stating the exact queue reference number and estimated wait window.

4.2. **Prohibition of Liability Admissions:**
Under no circumstances may automated messages or initial transfer scripts express an apology that admits fault, negligence, or operational liability on behalf of Kartway, its logistics providers, or merchant partners.
*   **Strictly Prohibited Language:**
    *   *"We apologize for our mistake."*
    *   *"We are sorry that our driver lost your package."*
    *   *"We regret that our product caused an injury."*
    *   *"We admit that this handling process failed."*
    *   *"We are responsible for this error."*
*   **Mandatory Neutral De-escalation Templates:**
    *   *"We understand this situation is frustrating, and we are connecting you to an operational specialist."*
    *   *"Thank you for bringing this issue to our attention. A team member is reviewing your file now."*
    *   *"We regret any inconvenience caused by this delay. Let me transfer you directly to [Target Team] to assist further."*

4.3. **Pre-Transfer Holding Script:**
When an interaction triggers an escalation, the automated assistant must present exactly one standardized transition message, selected based on the trigger code:

| Trigger Code | Mandatory Transfer Message |
| :--- | :--- |
| `human_requested` | *"I am connecting you with a Kartway Support Agent now. Please hold."* |
| `angry_or_abusive` | *"I am transferring this chat directly to a Team Lead to review your account."* |
| `repeat_contact` | *"As this is a recurring inquiry regarding order [ORN], a Team Lead has been assigned to assist you."* |
| `legal_or_regulatory` | *"Your account details are being transferred to our Legal Desk for direct handling."* |
| `product_safety` | *"Your safety is critical to us. I am transferring your report immediately to our Safety Desk."* |
| `refund_above_auto_cap` | *"This request requires management authorization. Transferring you to our Refund Approval Desk."* |
| `account_under_review` | *"I am transferring your request to an Account Specialist for verification."* |
| `delivery_dispute` | *"I am assigning your inquiry to an Agent to verify delivery logs with the carrier."* |
