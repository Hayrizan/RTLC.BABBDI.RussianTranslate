using System;
using System.IO;
using UnityEditor;
using UnityEngine;

public static class BuildRtlc
{
    public static void Build()
    {
        string[] assets = AssetDatabase.FindAssets("", new[] { "Assets/RTLC" });
        var paths = Array.ConvertAll(assets, AssetDatabase.GUIDToAssetPath);
        paths = Array.FindAll(paths, path => !AssetDatabase.IsValidFolder(path));
        Directory.CreateDirectory("BundleOutput");
        var map = new[] { new AssetBundleBuild { assetBundleName = "rtlc.bundle", assetNames = paths } };
        var manifest = BuildPipeline.BuildAssetBundles("BundleOutput", map,
            BuildAssetBundleOptions.ChunkBasedCompression | BuildAssetBundleOptions.StrictMode,
            BuildTarget.StandaloneWindows64);
        if (manifest == null)
            throw new InvalidOperationException("AssetBundle build failed.");

        var bundle = AssetBundle.LoadFromFile("BundleOutput/rtlc.bundle");
        if (!bundle || bundle.GetAllAssetNames().Length != paths.Length)
            throw new InvalidOperationException("AssetBundle readback failed.");
        foreach (string path in paths)
            if (path.EndsWith(".ttf") ? !bundle.LoadAsset<Font>(path) : !bundle.LoadAsset<TextAsset>(path))
                throw new InvalidOperationException("Unreadable bundle asset: " + path);
        Debug.Log("RTLC_BUNDLE_OK: " + paths.Length);
        bundle.Unload(true);
    }
}
