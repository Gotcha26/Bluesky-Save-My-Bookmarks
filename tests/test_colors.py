"""Tests pour core/colors.py"""
from core.colors import Colors


class TestColorsEnabled:
    def test_force_color_on(self):
        c = Colors(force_color=True)
        assert c.RED != ""
        assert c.GREEN != ""
        assert c.RESET != ""

    def test_force_color_off(self):
        c = Colors(force_color=False)
        assert c.RED == ""
        assert c.GREEN == ""
        assert c.RESET == ""
        assert c.BOLD == ""


class TestSemanticAliases:
    def test_aliases_set(self):
        c = Colors(force_color=True)
        assert c.OK == c.GREEN
        assert c.SUCCESS == c.GREEN
        assert c.ERROR == c.RED
        assert c.WARNING == c.YELLOW
        assert c.INFO == c.BLUE
        assert c.VALUE == c.CYAN
        assert c.KEY == c.WHITE
        assert c.PROMPT == c.YELLOW


class TestFormattingMethods:
    def setup_method(self):
        self.c = Colors(force_color=False)

    def test_success_contains_ok(self):
        result = self.c.success("Test réussi")
        assert "[OK]" in result
        assert "Test réussi" in result

    def test_error_contains_erreur(self):
        result = self.c.error("Problème")
        assert "[ERREUR]" in result
        assert "Problème" in result

    def test_warning_contains_attention(self):
        result = self.c.warning("Prudence")
        assert "[ATTENTION]" in result

    def test_info_contains_info(self):
        result = self.c.info("Détail")
        assert "[INFO]" in result


class TestMarkers:
    def setup_method(self):
        self.c = Colors(force_color=False)

    def test_ok_marker(self):
        assert "[OK]" in self.c.ok_marker()

    def test_error_marker(self):
        assert "[ERREUR]" in self.c.error_marker()

    def test_warn_marker(self):
        assert "[ATTENTION]" in self.c.warn_marker()


class TestInlineFormatting:
    def setup_method(self):
        self.c = Colors(force_color=False)

    def test_header(self):
        assert self.c.header("titre") == "titre"

    def test_title(self):
        assert self.c.title("section") == "section"

    def test_value(self):
        assert self.c.value("123") == "123"

    def test_key(self):
        assert self.c.key("label") == "label"

    def test_prompt(self):
        assert self.c.prompt("choix: ") == "choix: "


class TestUIElements:
    def setup_method(self):
        self.c = Colors(force_color=False)

    def test_separator_default(self):
        sep = self.c.separator()
        assert "-" * 60 in sep

    def test_separator_custom(self):
        sep = self.c.separator(char="=", width=40)
        assert "=" * 40 in sep

    def test_box_header(self):
        box = self.c.box_header("TITRE")
        assert "TITRE" in box
        assert "=" in box

    def test_menu_option(self):
        opt = self.c.menu_option("1", "Exporter")
        assert "1" in opt
        assert "Exporter" in opt

    def test_config_line(self):
        line = self.c.config_line("Clé", "Valeur")
        assert "Clé" in line
        assert "Valeur" in line
        assert ":" in line
