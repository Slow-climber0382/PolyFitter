# Repository setup still requiring owner/admin access

The integration can upload code but does not expose repository administration writes.
These settings must be verified in GitHub; their presence in this document does not
mean they are enabled.

0. Rename the repository in Settings → General → Repository name → `PolyFitter`. Update the upstream repository links in README, PRZECZYTAJ_MNIE and NOTICE after renaming.
1. For public open-source access, Settings → General → Change repository visibility → Public.
2. Settings → Pages → Build and deployment → Source: GitHub Actions.
3. Settings → Branches → protect `main` (or an active branch ruleset targeting main):
   - Require a pull request before merging; require at least 1 approval.
   - Require review from Code Owners; dismiss stale approvals on new commits.
   - Require conversation resolution.
   - Require status check `verify` after its first successful run.
   - Apply restrictions to administrators / disallow bypass.
   - Disallow force pushes and deletion.
4. Add a second trusted reviewer with write access if the owner will author PRs.
   Authors cannot approve their own PRs; CODEOWNERS currently names the owner.
5. Run the Pages workflow after enabling Pages, or let the next push to main trigger it.

Public repositories support protected branches on GitHub Free. Private repositories
may require a paid plan. Publication and review enforcement are separate settings.

Po polsku: ustaw publiczną widoczność, GitHub Pages z Actions i ochronę `main` wymagającą
PR, jednego niezależnego zatwierdzenia, recenzji CODEOWNERS oraz testu `verify`.
Włącz unieważnianie wcześniejszych zatwierdzeń po zmianie kodu, rozwiązywanie dyskusji,
zakaz force push i usuwania oraz stosowanie zasad także do administratorów.
Do PR autorstwa właściciela potrzebny będzie drugi uprawniony recenzent.
