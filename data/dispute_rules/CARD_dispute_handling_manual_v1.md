# Global Card Network Dispute & Chargeback Rules (v2.1)
**Document ID**: `DISP-RULE-2026-v2`  
**Effective Date**: 2026-01-01  
**Applies To**: Visa, Mastercard, and Domestic Debit Network Disputes  

---

## 1. General Dispute Filing Windows and Deadlines

### Rule CR-01: Standard Dispute Filing Window (120-Day Rule)
Customers and cardholders may dispute an unauthorized, fraudulent, or non-fulfillment transaction within **120 calendar days** from the original transaction processing date or from the agreed delivery date of merchandise/services.
- If `dispute_date - transaction_date <= 120 days`, the dispute is **eligible** for chargeback processing under network rules.
- If `dispute_date - transaction_date > 120 days`, network chargeback rights expire. The claim must be rejected as **OUTSIDE_CHARGEBACK_WINDOW** unless exceptional circumstances (e.g., merchant insolvency, delayed billing) apply.
- Chunk ID: `chunk-disp-window-001`

### Rule CR-02: Provisional Credit and Cardholder Rights
For disputes filed within 60 days of the statement date containing the disputed transaction:
- The issuing bank must issue provisional credit within 10 business days if the dispute involves unauthorized use or billing errors.
- Provisional credit may be withheld or reversed if the merchant provides compelling evidence or if friendly fraud is established.
- Chunk ID: `chunk-disp-credit-002`

---

## 2. Fraud Triage and Classification Standards

### Rule FT-01: True Fraud vs. Friendly Fraud
Disputes must be triaged into distinct operational queues based on fraud indicators:
1. **Third-Party / Account Takeover (True Fraud)**:
   - Cardholder asserts card was physically lost/stolen, or credentials compromised.
   - Device fingerprint mismatch, unrecognized IP geolocation (>500km from home), or rapid multi-merchant velocity.
   - Action: Immediate card block, reissue card, file chargeback under Reason Code 10.4 (Card-Absent Fraud).
2. **First-Party / Friendly Fraud**:
   - Transaction matches cardholder's usual device, recurring merchant history, or delivery address.
   - Action: Request cardholder clarification, review household purchase history, contact merchant for proof of delivery.
- Chunk ID: `chunk-fraud-triage-003`

### Rule FT-02: Compelling Evidence and Merchant Proof
A merchant can defeat an unauthorized transaction claim by submitting Compelling Evidence:
- Proof that the item was delivered to the cardholder's billing address or verified IP address.
- Prior undisputed transactions with the same device ID and payment credential within the past 12 months.
- Chunk ID: `chunk-compelling-evid-004`

---

## 3. Chargeback Reason Code Mapping

### Reason Code 10.4: Other Fraud — Card-Absent Environment
- **Description**: Cardholder did not authorize or participate in a card-not-present (eCommerce, MOTO) transaction.
- **Prerequisites**:
  - No 3D-Secure (3DS / OTP) authentication liability shift was successfully completed by the merchant.
  - Dispute filed within 120 days.
  - Fraud score >= 0.65 or confirmed unrecognized transaction.
- **Action**: Issue immediate chargeback to acquirer; recommend card cancellation.
- Chunk ID: `chunk-reason-10-4`

### Reason Code 13.1: Merchandise / Services Not Received
- **Description**: The cardholder was debited but the purchased goods or services were never delivered or provided.
- **Prerequisites**:
  - Expected delivery date has passed.
  - Cardholder attempted to resolve with the merchant or merchant is non-responsive.
  - Dispute filed within 120 days of expected delivery date.
- **Action**: Initiate chargeback under non-receipt provisions; provisional refund granted.
- Chunk ID: `chunk-reason-13-1`

### Reason Code 13.3: Defective or Not as Described
- **Description**: Goods delivered were damaged, counterfeit, or materially different from the merchant's description.
- **Prerequisites**:
  - Cardholder returned or attempted to return the goods.
  - Dispute filed within 120 days of receipt date.
- **Action**: Require return shipment tracking evidence before initiating chargeback.
- Chunk ID: `chunk-reason-13-3`

### Reason Code 10.5: Fraudulent Transaction — Card-Present
- **Description**: Counterfeit magnetic stripe or unauthorized contactless swipe without PIN verification.
- **Prerequisites**: EMV chip fallback transaction or non-PIN card present swipe.
- **Action**: Escalate to Fraud Operations for card skimming investigation.
- Chunk ID: `chunk-reason-10-5`
