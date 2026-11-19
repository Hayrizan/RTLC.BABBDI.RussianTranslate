namespace RTLC.BABBDI.RussianTranslate
{
    internal static class TranslationPatches
    {
        internal static TranslationCatalog Catalog;

        // Harmony binds __0 to the first string parameter for Unity text setters and TypewriterEffect.Run.
        public static void TranslateTextArgument(ref string __0)
        {
            TranslationCatalog catalog = Catalog;
            if (catalog != null && __0 != null)
                __0 = catalog.Translate(__0);
        }
    }
}
