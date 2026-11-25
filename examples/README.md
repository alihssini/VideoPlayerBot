# Examples

`acl/` shows the role files the app keeps in `data/acl/` (all ids are fake). You never have to create them:
the app writes them when you use `/promote`, `/addowner`, `/gpromote`, `/addbotowner`, `/use` — and on the first start it
moves `SUDO_USERS` of `.env` into `global_sudo.json`.

| File | Content |
|---|---|
| `acl/bot_owners.json` | bot owners added at runtime (root owners stay in `OWNER_USERS` of `.env`) |
| `acl/global_sudo.json` | SUDO users of every group |
| `acl/dm_targets.json` | per user: the group his private-chat commands go to (`/use`) |
| `acl/groups/<chat id>.json` | per group: title, owners, SUDO users |

A list entry is either a full object (`id`, `name`, `added_by`, `added_at`) or just the id — handy when you edit by hand.
To start with prepared roles, copy them before the first start:

```bash
mkdir -p data/acl && cp -r examples/acl/* data/acl/ && chmod -R go-rwx data   # then put your real ids in
```
