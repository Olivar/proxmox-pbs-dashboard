from pathlib import Path

from app.config import PbsInstance, PveInstance, parse_pbs_instances, parse_pve_instances
from app.settings_store import MASK, read_env, write_env


def test_parse_pve_instances_from_env_json() -> None:
    items = parse_pve_instances('[{"id":"pve1","name":"Principal","url":"https://pve.test:8006","token_id":"dash@pve!ro","token_secret":"secret","verify_tls":false}]')
    assert items[0].id == "pve1"
    assert items[0].verify_tls is False


def test_parse_multiple_pbs_instances_from_env_json() -> None:
    items = parse_pbs_instances('[{"id":"pbs1","name":"Principal","url":"https://pbs.test:8007","token_id":"dash@pbs!ro","token_secret":"secret","datastores":"store-a,store-b","node":"localhost","verify_tls":false}]')
    assert items[0].id == "pbs1"
    assert items[0].datastore_names == ["store-a", "store-b"]
    assert items[0].verify_tls is False


def test_write_env_preserves_masked_secret_and_stores_pves(tmp_path: Path) -> None:
    path = tmp_path / "dashboard.env"
    path.write_text('DASHBOARD_TITLE="Infra Proxmox"\nPBS_TOKEN_SECRET=secret\n', encoding="utf-8")
    current = [PveInstance(id="pve1", name="Principal", url="https://pve.test:8006", token_id="dash@pve!ro", token_secret="old-secret", verify_tls=False)]
    write_env(path, {"DASHBOARD_TITLE": "Novo Título", "PBS_TOKEN_SECRET": MASK}, [{"id":"pve1","name":"Principal","url":"https://pve.test:8006","token_id":"dash@pve!ro","token_secret":MASK,"verify_tls":False}], current)
    values = read_env(path)
    assert values["DASHBOARD_TITLE"] == "Novo Título"
    assert values["PBS_TOKEN_SECRET"] == "secret"
    assert "old-secret" in values["PVE_INSTANCES_JSON"]


def test_write_env_stores_multiple_pbs_and_preserves_masked_secret(tmp_path: Path) -> None:
    path = tmp_path / "dashboard.env"
    path.write_text("PBS_INSTANCES_JSON=[]\n", encoding="utf-8")
    pve = [PveInstance(id="pve1", name="Principal", url="https://pve.test:8006", token_id="dash@pve!ro", token_secret="secret")]
    pbs = [PbsInstance(id="pbs1", name="Principal", url="https://pbs.test:8007", token_id="dash@pbs!ro", token_secret="old-pbs-secret", datastores="store", verify_tls=False)]
    write_env(path, {}, [{"id":"pve1","name":"Principal","url":"https://pve.test:8006","token_id":"dash@pve!ro","token_secret":MASK,"verify_tls":True}], pve, [{"id":"pbs1","name":"Principal","url":"https://pbs.test:8007","token_id":"dash@pbs!ro","token_secret":MASK,"datastores":"store","node":"localhost","verify_tls":False}], pbs)
    values = read_env(path)
    assert "old-pbs-secret" in values["PBS_INSTANCES_JSON"]
