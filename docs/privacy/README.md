# Privacy operations — SwarRaksha

Operator-facing companion to the in-app Privacy Policy (apps/web/src/App.tsx).
Implements PLAN.md §11 (security & privacy non-negotiables) and the DPDP Act
2023 duties for a Data Fiduciary. User-facing promises live in the app; this
file is how the operator keeps them.

## What we hold, and for how long

| Data | Form at rest | Retention | Erasure |
|---|---|---|---|
| Account (email, name, language) | Postgres `users` | Life of account | Account deletion (Settings → Delete my account, or `DELETE /me`) removes the row and everything below |
| Voiceprints | **Encrypted embeddings only** (AES-256-GCM, `VOICEPRINT_ENC_KEY`); raw enrollment audio is deleted right after embedding | Life of account or until the voiceprint is deleted | `DELETE /voiceprints/{id}` wipes embedding + samples immediately |
| Checks (clip + live) | Scores, verdict, per-window aggregates — **never the call audio** | Life of account | Removed with account deletion |
| Challenges, reports, alerts | Postgres rows | Life of account | Removed with account deletion |
| Audit log | Actor, action, target, timestamp — no audio, no embeddings | 12 months | Operator purge job (manual until scheduled) |
| Server logs | Structured; no audio, no embeddings, no OTPs (dev-mode OTP logging is forbidden in production — `SWAR_DEV_MODE=0` is enforced by config validation) | 30 days at the host | Host log rotation |

Backups: daily database backup, 7-day retention (PLAN.md §10). A deletion is
honoured in backups as they rotate out — worst case 7 days after deletion the
data exists only in an expiring backup.

## Data-principal rights (DPDP)

Access, correction and erasure are self-serve in the app: **Download my data**
(`GET /me/export`, machine-readable JSON) and **Delete my account**
(`DELETE /me`). Grievances go to the privacy contact published in the in-app
Privacy Policy; acknowledge within 72 hours, resolve within 30 days.

## Breach response plan

1. **Detect & contain** — revoke JWT secret / rotate `VOICEPRINT_ENC_KEY`
   (voiceprints become unreadable — that is the point of encryption at rest),
   take the API offline if exfiltration is ongoing.
2. **Assess** — what data classes, how many users, were embeddings or only
   metadata involved. Embeddings alone, without the key, are not usable
   voiceprints.
3. **Notify** — inform the Data Protection Board of India and each affected
   user "without delay" (DPDP Act §8(6)) in plain language: what happened,
   what data, what we did, what they should do.
4. **Record** — incident timeline and decisions in this folder
   (`incident-YYYY-MM-DD.md`), kept out of the public repo if it contains
   personal data.
5. **Review** — post-incident fix list; update this plan.

## Consent

Enrollment is consent-first: a voiceprint can only be created inside the
voice owner's own OTP-verified session (see `docs/consent/`). No voice is
cloned for the eval set without written consent (PLAN.md §6.3).

## Open items before public launch

- [ ] Publish the privacy contact email + grievance officer in the in-app
      Privacy Policy (placeholder text is in App.tsx).
- [ ] Confirm backup job + retention at the chosen host.
- [ ] Schedule the audit-log purge.
