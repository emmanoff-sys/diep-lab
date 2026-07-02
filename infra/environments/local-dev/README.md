# local-dev — Not Ansible-Managed

**Status:** LIVE (delivered by WP-003-02).

Per Roadmap v1.0 §11.2's "Local Dev" row: *"Docker Compose; no Ansible...
fast iteration."* This environment has no `inventory.yml` and no
`terraform.tfvars` — it is provisioned entirely by
`templates/python-service/docker-compose.yml` (WP-003-02) on a developer's
own machine, never by the Ansible/Terraform path the other 7 environments
use.

See `templates/python-service/README.md` "Quick Start" for usage.
