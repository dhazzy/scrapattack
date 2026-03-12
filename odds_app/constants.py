SOURCE_PS3838 = "ps3838"
SOURCE_E_STAVE = "e_stave"

# Keep comparison sources centralized so adding a new bookmaker
# requires changing one place instead of multiple services.
DEFAULT_COMPARISON_SOURCES: tuple[str, str] = (SOURCE_PS3838, SOURCE_E_STAVE)
