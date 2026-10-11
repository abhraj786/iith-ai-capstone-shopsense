# Refund Authorisation and Escalation Matrix

**KARTWAY CUSTOMER OPERATIONS POLICY HANDBOOK**
**SECTION 7: REFUND AUTHORISATION MATRIX AND FINANCIAL DELEGATION LIMITS**

**7.1. Purpose and Principle of Net Calculation**
7.1.1. This policy defines the financial delegation limits for approving customer refunds, replacements, and goodwill credits across all Kartway retail operations.
7.1.2. The applicable approval tier is governed strictly by the final payable net refund amount. The net refund amount is calculated after deducting any applicable restocking fee and pickup fee from the gross transaction value.
7.1.3. This matrix applies universally to every refund category, reason code, and return type without exception, including claims for defective goods, logistics delays, non-delivery, damaged parcels, return-to-origin events, and pre-dispatch customer cancellations.

---

**7.2. Authorisation Tiers and Delegation Thresholds**
7.2.1. Refund requests must be routed and approved strictly within the following cumulative financial bands:
* **Tier 1 (Automated Assistant / Customer Support Agent):** Up to 2,000 rupees.
* **Tier 2 (Team Lead):** Above 2,000 rupees and up to 10,000 rupees.
* **Tier 3 (Operations Manager):** Above 10,000 rupees and up to 50,000 rupees.
* **Tier 4 (Finance Department):** Above 50,000 rupees.

---

**7.3. Automated Assistant Operational Boundaries**
7.3.1. The automated assistant (bot orchestration system) possesses approval authority strictly up to 2,000 rupees.
7.3.2. The automated system is programmatically barred from approving any refund exceeding 2,000 rupees under any circumstance.
7.3.3. Customer account classification, lifetime order frequency, priority membership level, Net Promoter Score, or live sentiment telemetry shall not override the 2,000 rupees hard ceiling for automated processing. Any transaction exceeding 2,000 rupees must trigger an immediate ticket handoff to Tier 2 human review.

---

**7.4. Replacement Orders**
7.4.1. An item replacement carries the identical financial exposure as a cash-out refund.
7.4.2. Authorisation for a merchant replacement is governed by the exact same delegation tiers established in Clause 7.2.1, pegged directly to the net amount paid by the customer for the original line item.

---

**7.5. Pre-Dispatch Cancellations and Cash-on-Delivery Protocol**
7.5.1. Cancellations executed before parcel dispatch for prepaid orders (credit card, debit card, unified payments interface, net banking, or gift cards) fall within the thresholds detailed in Clause 7.2.1 and require sign-off matching the net transaction value.
7.5.2. A Cash-on-Delivery (COD) order cancelled before dispatch carries a payable refund balance of zero rupees. Because no customer funds have been collected, pre-dispatch COD cancellations generate no refund remittance and require zero approval tier authorisation.

---

**7.6. Goodwill Credits**
7.6.1. Goodwill credits operate independently of statutory and transactional refund flows and are bound by a dedicated threshold capped at 500 rupees per order.
7.6.2. Under no circumstance may a goodwill credit exceed 500 rupees for a single order identifier.
7.6.3. Exactly one goodwill credit is permitted per order. Subsequent attempts to disburse goodwill credit against an existing order identifier will be locked by the core payment gateway.
7.6.4. Goodwill credits must be disbursed solely to the customer’s registered Kartway wallet. Cash payouts, external bank transfers, and original payment method reversals are prohibited for goodwill credits.
7.6.5. Authority to disburse a goodwill credit up to the 500 rupees cap is delegated to any operational tier, including the automated assistant acting alone.
7.6.6. Stacking restriction: A goodwill credit cannot be combined or stacked with a full refund on the same order identifier. When a full refund of the amount paid is processed, the system must disable and invalidate any concurrent goodwill allocation for that order.
