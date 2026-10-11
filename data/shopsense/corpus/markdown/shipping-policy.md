# Shipping, Delivery and Lost-Parcel Policy

# KARTWAY CUSTOMER OPERATIONS POLICY HANDBOOK
**Document Reference:** COP-FUL-2024-V3
**Section:** Fulfillment, Transit Operations, and Delivery Dispute Resolution
**Effective Date:** 01 November 2024
**Applies To:** Customer Support Tier 1, Support Operations, Logistics Coordination, Automated Support Engines

---

### 1.0 DELIVERY SERVICE LEVEL AGREEMENTS (SLAs)

#### 1.1 SLA Determination
The delivery promise date is calculated automatically at checkout based on the order placement timestamp, the selected service tier, and the destination pin code classification (Metro vs. Non-Metro).

#### 1.2 Transit Windows by Service Tier and Region
Support agents must consult the following fixed transit day allowances (measured continuously from the calendar date the order is placed):

*   **1.2.1 Express Delivery Tier**
    *   Metro Destination: 2 calendar days from order date.
    *   Non-Metro Destination: 3 calendar days from order date.
*   **1.2.2 Standard Delivery Tier**
    *   Metro Destination: 5 calendar days from order date.
    *   Non-Metro Destination: 7 calendar days from order date.
*   **1.2.3 Economy Delivery Tier**
    *   Metro Destination: 10 calendar days from order date.
    *   Non-Metro Destination: 10 calendar days from order date.

---

### 2.0 SHIPMENT DELAYS AND GOODWILL COMPENSATION

#### 2.1 Definition of a Delayed Shipment
A shipment is classified as "Delayed" when the final physical delivery scan occurs after the promised date calculated under Section 1.2.

#### 2.2 Retention Compensation Schedule
When a shipment arrives after the promised date and the customer retains the merchandise, agents are authorized to issue compensation exclusively in the form of a non-withdrawable credit to the customer's Kartway Wallet. Cash refunds or external chargebacks are strictly prohibited for late-delivery compensation.

*   **2.2.1 Delay of 1 to 2 Calendar Days Past Promised Date:**
    *   Remedy: Standard written apology via email/notification.
    *   Wallet Credit: 0 INR (no financial credit authorized).
*   **2.2.2 Delay of 3 to 5 Calendar Days Past Promised Date:**
    *   Remedy: Written apology and a 100 INR credit to the Kartway Wallet.
*   **2.2.3 Delay of 6 or More Calendar Days Past Promised Date:**
    *   Remedy: Written apology and a 250 INR credit to the Kartway Wallet.

---

### 3.0 LOST-IN-TRANSIT (LIT) DECLARATIONS

#### 3.1 Lost-in-Transit Threshold
A shipped package that has not received a terminal delivery scan by **10 calendar days past its original promised delivery date** must be declared Lost in Transit (LIT). Prior to the expiration of this 10-day post-promise window, agents may not record the parcel as lost.

#### 3.2 Customer Remedies
Upon meeting the 10-day LIT threshold, the agent must offer the customer their choice of:
1.  A 100% refund of the transaction amount to the original payment source.
2.  A zero-cost replacement order dispatched via the fastest available tier.

#### 3.3 Authorization Hierarchy
Refunds and replacement orders under Section 3.2 must be approved by the agent tier assigned to the monetary value of the underlying order, in accordance with the Kartway Financial Delegation Matrix (Tier 1 Support up to 2,000 INR; Tier 2 Lead up to 10,000 INR; Operations Manager above 10,000 INR).

---

### 4.0 DISPUTED DELIVERY SCANS ("FALSE DELIVERY")

#### 4.1 Reporting Deadline
A customer disputing a terminal "Delivered" scan (claiming non-receipt despite a carrier confirmation) must file a claim within **3 calendar days** of the delivery scan timestamp. Claims submitted after 3 calendar days must be rejected under standard policy.

#### 4.2 Automated Assistant Restriction
The Kartway automated virtual assistant is strictly prohibited from resolving, closing, or issuing payouts for disputed delivery claims. The automated flow must create an escalation ticket and transfer the case to a human support agent.

#### 4.3 Human Investigation Procedure
*   **4.3.1 Carrier Contact:** The human agent must initiate an off-line delivery trace with the logistics partner within 4 business hours of ticket assignment.
*   **4.3.2 Carrier Claim SLA:** Carriers have contractually bounded business-day response windows to produce physical proof of delivery (signed run sheet, geo-coordinates, or OTP validation):
    *   Bluedart: 2 business days
    *   Delhivery: 3 business days
    *   Ecom Express: 3 business days
    *   IndiaPost: 5 business days
    *   XpressBees: 4 business days
*   **4.3.3 Dispute Resolution Window:** The total investigation must be concluded, and a final resolution (validation of delivery or authorization of LIT remediation under Section 3.2) provided to the customer, within **5 business days** of the ticket's creation date.

---

### 5.0 ADDRESS CHANGE CUTOFFS

#### 5.1 Permitted Status Window
A customer or support agent may alter the delivery address only while the order remains in the `PLACED` status.

#### 5.2 Hard Cutoff
Once an order transitions out of `PLACED` (including but not limited to `PACKED`, `MANIFESTED`, or `SHIPPED`), the address field is permanently locked. Under no circumstances may an agent modify address details, redirect parcels in transit, or request in-flight courier changes once the package has shipped. If the customer cannot receive the parcel at the registered address, it must proceed to attempted delivery, fail, return to origin, and be reordered.
