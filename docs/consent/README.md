# Voiceprint enrollment consent

Implements PLAN.md §6.3 and §11: **no person's voice is enrolled or cloned
without explicit consent.** Signed forms live outside git (they contain
personal data); this folder holds the process and the template text only.

## How consent works in the product

1. Enrollment (`POST /voiceprints`) is only possible inside the voice
   owner's **own OTP-verified session** — you cannot enroll someone else's
   voice from your account.
2. Before recording, the app shows the consent text below; the enrollment
   timestamp is stored as `consent_at` on the voiceprint row.
3. Withdrawal is immediate and self-serve: deleting the voiceprint wipes the
   encrypted embedding and any stored samples. Deleting the account wipes
   all voiceprints.

## Consent text (shown in-app before enrollment)

> I agree to enroll my voice in SwarRaksha.
> - SwarRaksha will record 3 short samples of my voice and turn them into a
>   mathematical voiceprint (an embedding), stored encrypted.
> - My raw recordings are deleted after the voiceprint is created.
> - The voiceprint is used only to check whether a caller claiming to be me
>   really sounds like me.
> - I can delete my voiceprint or my whole account at any time in Settings,
>   which erases it permanently.
> - My voice will never be cloned, sold, or used to train models unless I
>   separately agree in writing (research donation is a different form).

## Research / eval-set donation (separate, written)

Cloning a voice for the self-generated eval set (PLAN.md §6.3) requires a
**separate written consent** naming: the person, the cloner tool(s), that
clones are used only to test detection, storage location of the samples,
and a deletion date. Template fields:

- Full name · Email · Date
- "My voice may be cloned with: ______ (tool names)"
- "Clones and samples are used only for detection testing."
- "Delete all my samples and clones by: ______ (date)"
- Signature

One form per person, stored by the operator outside this repository.
