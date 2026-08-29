import pytest

from gauntpy.secret_code_verifier import main, verify_secret_code


def test_verifier_accepts_the_known_rom_code(capsys):
    assert main([
        "ALINSA", "FB9-AD9",
    ]) == 0
    assert capsys.readouterr().out == (
        "valid: FB9-AD9 (maze 73, trick 5, challenge 0x5a)\n"
    )


def test_verifier_rejects_a_mismatched_code(capsys):
    assert main([
        "ALINSA", "000-000",
    ]) == 1
    assert "does not match the submitted name" in capsys.readouterr().out


def test_verifier_decodes_state_without_it_being_supplied():
    assert verify_secret_code("DARREN STONE", "8KW-9BS") == (
        True, 57, 9, 0x5A,
    )


@pytest.mark.parametrize("code", ["W1YOGNO", "ABC-IOV", "ABC-DEFZ"])
def test_verifier_rejects_impossible_rom_code_shapes(code):
    with pytest.raises(ValueError):
        verify_secret_code("ALINSA", code)
