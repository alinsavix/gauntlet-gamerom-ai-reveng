from gauntpy.secret_code_verifier import main


def test_verifier_accepts_the_known_rom_code(capsys):
    assert main([
        "ALINSA", "FB9-AD9", "--maze", "73", "--trick", "5",
        "--challenge", "0x5A",
    ]) == 0
    assert capsys.readouterr().out == "valid: FB9-AD9\n"


def test_verifier_rejects_a_mismatched_code(capsys):
    assert main([
        "ALINSA", "000-000", "--maze", "73", "--trick", "5",
        "--challenge", "0x5A",
    ]) == 1
    assert "expected FB9-AD9" in capsys.readouterr().out
