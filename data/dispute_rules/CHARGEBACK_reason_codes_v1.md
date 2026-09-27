# Comprehensive Chargeback Reason Codes Reference
**Document ID**: `CB-CODES-2026-v1`  
**Applicability**: Card Dispute Resolution Guidelines  

---

## 1. Fraud Category Codes

### Code 4837 / 10.4: No Cardholder Authorization
- Used when a cardholder explicitly denies making or authorizing the transaction.
- Standard timeframe: 120 calendar days from transaction date.
- Key criteria:
  - If 3DS (3-Domain Secure) authentication was validated, liability remains with issuer; chargeback is denied unless merchant is in an excessive fraud program.
  - If transaction was standard SSL e-commerce without OTP/3DS, liability lies with acquirer/merchant.
- Chunk ID: `chunk-cb-4837-noauth`

### Code 4840 / 10.5: Fraudulent Processing of Transactions
- Used when multiple authorizations or invalid account number processing occur.
- Standard timeframe: 120 calendar days from transaction date.
- Chunk ID: `chunk-cb-4840-proc`

---

## 2. Consumer Dispute & Non-Fulfillment Category Codes

### Code 4853 / 13.1: Goods or Services Not Provided
- The cardholder engaged in the transaction, but merchandise was not received by the promised delivery date.
- Cardholder must wait until agreed delivery date has elapsed before filing.
- Window: 120 days from transaction date or agreed delivery date, whichever is later (maximum 540 days from original transaction date).
- Chunk ID: `chunk-cb-4853-notrec`

### Code 4855 / 13.2: Cancelled Recurring Transaction
- The cardholder withdrew authorization for recurring billing (e.g., subscription, gym membership), but the merchant continued billing.
- Cardholder must provide date and method of cancellation notification to merchant.
- Timeframe: 120 days from the latest disputed billing date.
- Action: Immediate merchant dispute; require cardholder to submit cancellation confirmation email.
- Chunk ID: `chunk-cb-4855-recurring`

### Code 4834 / 12.5: Point of Interaction Error / Duplicate Charge
- The cardholder was billed multiple times for a single purchase, or billed an incorrect amount.
- Timeframe: 120 days from transaction date.
- Evidence required: Statement showing multiple identical charges with same authorization code or receipt showing differing amount.
- Chunk ID: `chunk-cb-4834-duplicate`
