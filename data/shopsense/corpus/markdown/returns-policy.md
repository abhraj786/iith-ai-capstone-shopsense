# Kartway Returns and Refunds Policy

# Section 2: Returns and Refunds Policy

### 2.1 Base Valuation Rule
All refunds issued by Kartway must be calculated strictly against the net amount the customer paid for the specific item in the order (inclusive of applied discounts, promotions, and taxes). Under no circumstance shall a refund calculation reference or default to the current active list price of the product on the marketplace.

### 2.2 Return Windows by Category
The baseline marketplace return window is 30 days, calculated from the carrier delivery timestamp. However, category-specific operational windows supersede the baseline window as configured below:
* **2.2.1 Electronics:** 15 calendar days from delivery date.
* **2.2.2 Home & Kitchen:** 30 calendar days from delivery date.
* **2.2.3 Apparel:** 45 calendar days from delivery date.
* **2.2.4 Beauty:** 10 calendar days from delivery date.
* **2.2.5 Sports & Outdoors:** 30 calendar days from delivery date.
* **2.2.6 Toys:** 20 calendar days from delivery date.
* **2.2.7 Groceries:** Non-returnable (physical return not accepted under any circumstances).
* **2.2.8 Furniture:** 7 calendar days from delivery date.

### 2.3 Condition Requirements
To qualify for a standard return, items must be intact, include all original tags, manuals, accessories, and be housed in their original manufacturer packaging. Unopened items must show no broken seal. Opened items are accepted only within permissible categories subject to the restocking fee schedule detailed in Clause 2.5. Products showing customer-induced physical damage, alterations, or missing serial numbers will be rejected during reverse-logistics intake.

### 2.4 Return Pickup Fees for Change-of-Mind Requests
Where a return request is submitted under the reason code `changed_mind`, the customer is responsible for the reverse transit cost, which is deducted directly from the refund balance. The standard pickup fee is 99 rupees, with the following exceptions:
* **2.4.1 Apparel:** 0 rupees (free return pickup).
* **2.4.2 Furniture:** 499 rupees.
* **2.4.3 All Other Eligible Categories:** 99 rupees.

### 2.5 Restocking Fees for Opened Items (Change-of-Mind Returns)
If an item returned under the `changed_mind` reason code has had its factory seal broken or packaging opened, a category restocking fee applies. The fee is calculated as a direct percentage of the net amount paid by the customer, rounded to the nearest integer rupee:
* **2.5.1 Electronics:** 15% restocking fee.
* **2.5.2 Home & Kitchen:** 10% restocking fee.
* **2.5.3 Apparel:** 0% restocking fee (no restocking deduction).
* **2.5.4 Beauty:** Opened items are strictly non-returnable for change of mind. Requests must be rejected.
* **2.5.5 Sports & Outdoors:** 12% restocking fee.
* **2.5.6 Toys:** 5% restocking fee.
* **2.5.7 Furniture:** 20% restocking fee.

### 2.6 Refund Reason Classifications and Shipping Liability
Agents must categorize all refund workflows into one of the following official reason codes:

* **2.6.1 damaged:** The item was delivered damaged and the customer submitted digital photographic evidence within the category's defect claim window. Groceries are refunded exclusively via photographic proof without physical reverse shipping. Kartway issues a 100% refund of the amount paid. Return shipping costs are paid by Kartway.
* **2.6.2 wrong_item:** A SKU mismatch occurred where the delivered item differs from the invoice. Kartway issues a 100% refund of the amount paid. Return shipping costs are paid by Kartway.
* **2.6.3 quality:** The product exhibits internal component defects, manufacturing flaws, or material discrepancies from the product display page. Kartway issues a 100% refund of the amount paid. Return shipping costs are paid by Kartway.
* **2.6.4 not_delivered:** The package has been formally designated Lost in Transit (LIT) by the carrier, or a non-receipt dispute has been decided in the customer’s favor. Kartway issues a 100% refund of the amount paid. Physical return is not applicable.
* **2.6.5 late_delivery:** The shipment arrived after the promised delivery date displayed at checkout, and the customer refused receipt or initiated an immediate return. (Customers opting to retain the product are ineligible for a refund and must be issued the standard delay credit instead). Kartway issues a 100% refund of the amount paid. Return shipping costs are paid by Kartway.
* **2.6.6 changed_mind:** The customer elects to return an item without defect or operational fault. The request must fall strictly within the category return window defined in Clause 2.2. The customer funds reverse logistics via the category pickup fee (Clause 2.4). Kartway issues a refund of 100% of the amount paid, less the applicable opened-item restocking fee (Clause 2.5) and less the return pickup fee.
* **2.6.7 cancelled_before_dispatch:** The order was cancelled by the customer or the automated intake queue prior to fulfillment and manifest generation. Kartway issues a 100% refund of the amount paid. Physical return is not applicable.

### 2.7 Worked Refund Calculation Example
A customer purchases a Home & Kitchen appliance for an invoiced payment amount of 8,000 rupees and subsequently requests a return under `changed_mind` after opening the packaging:
1. Base amount paid: 8,000 rupees.
2. Category restocking fee for opened Home & Kitchen (10% of 8,000 rupees): 800 rupees deduction.
3. Standard category return pickup fee: 99 rupees deduction.
4. Total deduction: 800 rupees + 99 rupees = 899 rupees.
5. Final approved refund: 8,000 rupees − 899 rupees = 7,101 rupees.

### 2.8 Refund Processing Service-Level Agreements (SLAs)
Upon return inspection sign-off or immediate claim approval by customer operations, the refund disbursement timeline is governed strictly by the original transaction instrument:
* **2.8.1 card:** 5 to 7 business days, credited back to the originating debit or credit card.
* **2.8.2 upi:** 3 business days, disbursed to the initiating Virtual Payment Address (VPA) / UPI account.
* **2.8.3 wallet:** 24 hours, credited directly to the customer’s active Kartway balance.
* **2.8.4 cod:** 10 business days, disbursed via NEFT/IMPS to the customer-provided bank account details.
* **2.8.5 netbanking:** 5 to 7 business days, routed to the source banking institution account.
