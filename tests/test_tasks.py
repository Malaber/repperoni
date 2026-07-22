from tasks import _latest_stable_version, _version_values


def test_versioning_ignores_non_release_tags():
    tags = ["v0.1.0", "v0.1.2", "v0.2.0-rc.5", "other"]
    assert _latest_stable_version(tags) == "0.1.2"
    assert _version_values("main", 9, tags)["release_version"] == "0.1.3"


def test_branch_versions_avoid_existing_rc_tags():
    values = _version_values("feature", 5, ["v0.1.0", "v0.1.1-rc.5"])
    assert values == {
        "base_version": "0.1.1",
        "release_version": "0.1.1-rc.6",
        "git_tag": "v0.1.1-rc.6",
    }
