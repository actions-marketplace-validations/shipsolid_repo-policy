from repo_policy.diff import Change
from repo_policy.render import render_plan


def test_render_plan_reports_no_changes():
    output = render_plan("acme/widgets", "main", [])
    assert "Repository: acme/widgets" in output
    assert "Branch: main" in output
    assert "No changes required." in output


def test_render_plan_shows_symbols_per_action():
    changes = [
        Change(field="linear_history", current_value=False, desired_value=True, action="add"),
        Change(field="allow_force_push", current_value=True, desired_value=False, action="remove"),
        Change(field="pull_requests", current_value="1 approval", desired_value="2 approvals", action="modify"),
    ]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Linear history" in output
    assert "- Force pushes" in output
    assert "~ Pull request requirements" in output
    assert "3 changes required." in output


def test_render_plan_singular_change_count():
    changes = [Change(field="linear_history", current_value=False, desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "1 change required." in output


def test_render_plan_shows_enforce_admins_label():
    changes = [Change(field="enforce_admins", current_value=False, desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Admin enforcement" in output


def test_render_plan_shows_conversation_resolution_label():
    changes = [Change(field="required_conversation_resolution", current_value=False,
                       desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Conversation resolution" in output
