## ⚠ FROZEN EXPLORATORY RUN — NOT THE FINAL E2E VALIDATION

- This was an **exploratory run** (executed 2026-10-08).
- It used an **incorrect geographic scope**: disasters across India, all served from AASHRAY's
  Mumbai warehouses and responders.
- Many routes were **unrealistically long** (mean 1,103 km, maximum 2,143 km), i.e. interstate
  logistics, which is not the operational scenario AASHRAY is meant to validate.
- It is **NOT** the final 100-scenario E2E validation, and its results **must not be used as the
  final AASHRAY E2E results**. The final experiment is the Maharashtra-only local-response run in
  `experiments/e2e_100_maharashtra/`.
- The directory was renamed from `experiments/e2e_100/` on 2026-10-08; its contents are otherwise
  preserved unchanged (paths inside its files still say `e2e_100`).

