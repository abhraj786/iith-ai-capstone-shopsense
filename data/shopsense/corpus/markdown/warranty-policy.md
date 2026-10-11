# Warranty and Replacement Policy

**KARTWAY OPERATIONAL POLICY MANUAL**
**Document Ref:** POL-OPS-WAR-2024-V4
**Owner:** Customer Operations Policy Team
**Audience:** Tier 1 and Tier 2 Customer Support Agents, Resolution Specialists
**Subject:** Post-Delivery Warranty Adjudication and Processing

---

### 1.0 Scope and Category Eligibility

* **1.1 Covered Categories:** Warranty claims may only be opened for items categorized in the Kartway product catalog under the following five departments:
  * 1.1.1 Electronics
  * 1.1.2 Home & Kitchen
  * 1.1.3 Sports & Outdoors
  * 1.1.4 Toys
  * 1.1.5 Furniture

* **1.2 Excluded Categories:** The following departments carry no warranty coverage under any circumstance:
  * 1.2.1 Apparel
  * 1.2.2 Beauty
  * 1.2.3 Groceries

* **1.3 Listing Error Override:** If a product classified under an excluded category listed in Clause 1.2 displays a warranty duration on its product display page (PDP), this constitutes an operational listing error.
  * 1.3.1 Agents must inform the customer that no coverage applies.
  * 1.3.2 Agents must reject the warranty intake ticket under reason code `ERR_CAT_EXCLUDED`.
  * 1.3.3 The presence of a warranty badge or duration on an excluded category item does not create coverage liability for Kartway or the merchant.

---

### 2.0 Coverage Durations and Baseline Dates

* **2.1 Determination of Term:** The valid warranty term for eligible items is dictated strictly by the duration stamped on the order invoice and product listing snapshot at the time of purchase. Valid values are exclusively:
  * 2.1.1 None (0 months)
  * 2.1.2 6 months
  * 2.1.3 12 months
  * 2.1.4 24 months

* **2.2 Commencement Date:** All warranty periods are counted from the recorded carrier delivery date (`DLV_TS`). The order creation date, dispatch date, and invoice generation date must not be used as the starting point.

* **2.3 Expired Status:** Any claim logged at `DLV_TS` plus the exact monthly duration plus 1 calendar day is past coverage and must be rejected under code `WAR_STATUS_EXPIRED`.

---

### 3.0 Fulfillment Method and Handler Allocation

* **3.1 Kartway-Fulfilled Inventory:**
  * 3.1.1 If the order displays the fulfillment tag `FULFILLED_BY_KARTWAY` (inventory dispatched from Kartway Central Hubs), the claim is owned and managed directly by the Kartway Warranty Desk.
  * 3.1.2 The agent must initiate an internal warranty service request (`WSR`) within the agent console.

* **3.2 Seller-Fulfilled Inventory:**
  * 3.2.1 If the order displays the fulfillment tag `FULFILLED_BY_SELLER` (marketplace dropship), coverage is administered directly by the manufacturer’s authorized service network.
  * 3.2.2 The Kartway agent must not attempt internal booking. The agent must intake the customer's diagnostic form and transmit the claim packet to the external manufacturer network via the Merchant Integration Portal within 4 business hours.
  * 3.2.3 The agent must provide the customer with the external manufacturer reference identifier and authorized drop-off/inspection locations.

---

### 4.0 Conditions Voiding Warranty

A claim must be denied immediately under code `WAR_VOID_REJECT` if the item exhibits any of the following technical indicators during initial photo triage or hub intake assessment:

* **4.1 Unauthorized Modification:** Breaking of manufacturer tamper seals, custom firmware flashing, or physical repairs conducted by third-party facilities not certified by Kartway or the original equipment manufacturer.
* **4.2 Physical and Environmental Abuse:** Cracked housings, severed wiring, bent internal frames, or impact fractures resulting from drops.
* **4.3 Liquid Contamination:** Triggered Liquid Contact Indicators (LCIs), visible corrosion on circuit boards, or moisture within internal sealed housings (except for products explicitly rated IP68 or higher operated within documented operational tolerances).
* **4.4 Serial and Identifier Mismatch:** Inability to verify the physical serial number, IMEI, or asset tag against the serial recorded in the Kartway shipping manifest (`SHIP_MANIFEST_SN`).
* **4.5 Power Surge and Commercial Use:** Burn marks on power inputs resulting from non-certified power supplies, or continuous non-domestic use of units designated on the product page as domestic-rated only.

---

### 5.0 Resolution Determination (Replace vs. Repair)

Agents must strictly apply the following operational logic when deciding between item replacement and item repair for valid, unvoided claims:

```
Claim Approved (Within Coverage Term)
│
├── Failure Date <= 30 Days from Delivery Date?
│   ├── YES ──> ISSUE REPLACEMENT
│   │
│   └── NO (Failure Date > 30 Days from Delivery Date)
│       │
│       ├── Amount Paid < 1,500 Rupees?
│       │   ├── YES ──> ISSUE REPLACEMENT
│       │   │
│       │   └── NO (Amount Paid >= 1,500 Rupees)
│       │       │
│       │       ├── Can repair be completed in <= 14 business days?
│       │       │   ├── YES ──> ROUTE TO REPAIR
│       │       │   └── NO  ──> ISSUE REPLACEMENT
```

* **5.1 The 30-Day Failure Threshold:** Any functional, electrical, or structural failure reported within 30 days of the carrier delivery date (`DLV_TS`) is categorized as Early Failure and must be granted a unit replacement. Repair must not be offered.
* **5.2 Post-30-Day Adjudication:** For failures reported on day 31 through the end of the warranty term:
  * 5.2.1 The standard operational pathway is repair.
  * 5.2.2 **Low-Value Exception:** If the total unit price paid by the customer (inclusive of item discounts, exclusive of shipping fees) was under 1,500 rupees, agents must not route the unit to repair. The unit must be routed to replacement.
  * 5.2.3 **Repair Lead-Time Exception:** If the service center assesses that spare parts are back-ordered or labor capacity prevents completion within 14 business days, the repair ticket must be closed out and converted to a replacement.

---

### 6.0 Service Level Agreements (SLAs) and Turnaround Commitments

* **6.1 Replacement Dispatch Commitment:**
  * Once a replacement resolution is authorized, the new unit must be dispatched from a Kartway hub within exactly 3 business days of the approval timestamp.
  * If identical inventory is unavailable, the agent must trigger a refund following standard catalog stock-out procedures.

* **6.2 Repair Turnaround Commitment:**
  * The end-to-end repair cycle—measured from the moment the defective unit is received at the repair facility to the moment the repaired item is handed to the logistics carrier for return shipment—must not exceed 14 business days.
  * If the repair facility reaches day 10 without components to clear quality assurance, the ticket must be escalated immediately to trigger a replacement under Clause 5.2.3.

---

### 7.0 Financial Approval and Authority Matrix

* **7.1 Replacement Delegation:** Replacements carry direct inventory financial write-offs. A replacement order must be approved at the identical operational authority tier required for a monetary refund of the original amount paid:
  * 7.1.1 **Tier 1 Support Agent:** Approvals up to 2,000 rupees.
  * 7.1.2 **Tier 2 Team Lead:** Approvals from 2,001 rupees to 10,000 rupees.
  * 7.1.3 **Operations Manager:** Approvals above 10,000 rupees.
* **7.2 Prohibition on Downgrading:** Agents may not bypass approval limits by authorizing alternative, lower-spec SKUs. Replacement units must always be an identical SKU matching the original purchase.
