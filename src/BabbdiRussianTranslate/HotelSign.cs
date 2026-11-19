using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

namespace RTLC.BABBDI.RussianTranslate
{
    internal static class HotelSign
    {
        private const string Replacement = "RTLC Hotel Lettering";
        private const float Front = 152.83684f;
        private const float Back = 152.45564f;

        public static bool Apply(out bool verticalInstalled)
        {
            verticalInstalled = false;
            var sign = GameObject.Find("SM_Scene_A_HotelSigns_00");
            if (sign == null || sign.transform.Find(Replacement) != null)
                return false;

            var renderer = sign.GetComponent<MeshRenderer>();
            var filter = sign.GetComponent<MeshFilter>();
            if (renderer == null || filter == null || filter.sharedMesh == null ||
                filter.sharedMesh.name != "Combined Mesh (root: scene) 19")
                return false;

            var materials = renderer.sharedMaterials;
            var transparentShader = Shader.Find("UI/Default");
            if (materials.Length != 2 || materials[1] == null ||
                materials[1].name != "Hool 1" || transparentShader == null)
                return false;

            if (materials[0] != null && materials[0].name == "Hool" &&
                materials[0].HasProperty("_BC") && materials[0].GetTexture("_BC")?.name == "HoolSign")
            {
                BuildBlade(sign.transform, materials[0]);
                verticalInstalled = true;
                materials[0] = new Material(transparentShader) { color = Color.clear };
            }

            var geometry = new Geometry();
            geometry.AddRow("upper", -21.73f, -20.03f, -7.31f, 5.76f);
            geometry.AddRow("lower", -24.35f, -22.57f, -7.11f, 4.42f);

            var child = new GameObject(Replacement);
            child.transform.SetParent(sign.transform, true);
            child.AddComponent<MeshFilter>().sharedMesh = geometry.Build();
            child.AddComponent<MeshRenderer>().sharedMaterial = materials[1];

            // The second batched submesh contains only the original letters.
            materials[1] = new Material(transparentShader) { color = Color.clear };
            renderer.sharedMaterials = materials;
            return true;
        }

        private static void BuildBlade(Transform parent, Material material)
        {
            var geometry = new Geometry();
            geometry.AddFrame(new Vector3(157.98f, 56.41f, 23.30f),
                new Vector3(159.59f, 77.05f, 26.92f), new Rect(224f, 385f, 3f, 60f));
            geometry.AddBox(new Vector3(158.12f, 56.58f, 23.49f),
                new Vector3(159.45f, 76.88f, 26.73f), new Rect(176f, 177f, 12f, 8f), 0f);

            var paint = new Rect(116f, 53f, 19f, 65f);
            for (int i = 0; i < 6; i++)
            {
                float top = 76.18f - i * 3.27f;
                float lean = (top - 57.6f) * 0.025f;
                AddLetter(false, 159.78f, 159.44f);
                AddLetter(true, 157.77f, 158.13f);

                void AddLetter(bool reverse, float front, float back)
                {
                    if (i < 4)
                        geometry.AddSmoothLetter(i != 0, top - 2.37f, top, 23.94f - lean, 26.32f - lean,
                            front, back, paint, reverse);
                    else
                        geometry.AddRow("hool_l", top - 2.37f, top, 23.94f - lean, 26.32f - lean,
                            front, back, paint, reverse, 1024f);
                }
            }

            var diffuse = Shader.Find("Standard") ?? Shader.Find("Legacy Shaders/Diffuse");
            var bladeMaterial = diffuse != null ? new Material(diffuse) : new Material(material);
            if (diffuse != null)
                bladeMaterial.mainTexture = material.GetTexture("_BC");
            bladeMaterial.color = new Color(0.48f, 0.48f, 0.48f, 1f);
            if (bladeMaterial.HasProperty("_Glossiness"))
                bladeMaterial.SetFloat("_Glossiness", 0f);
            if (bladeMaterial.HasProperty("_EmissionColor"))
                bladeMaterial.SetColor("_EmissionColor", Color.black);
            if (bladeMaterial.HasProperty("_SpecularHighlights"))
                bladeMaterial.SetFloat("_SpecularHighlights", 0f);
            bladeMaterial.EnableKeyword("_SPECULARHIGHLIGHTS_OFF");
            bladeMaterial.DisableKeyword("_EMISSION");

            var blade = new GameObject("RTLC Vertical Hotel Sign");
            blade.transform.SetParent(parent, true);
            blade.transform.position += Vector3.forward * 0.40f;
            blade.AddComponent<MeshFilter>().sharedMesh = geometry.Build();
            blade.AddComponent<MeshRenderer>().sharedMaterial = bladeMaterial;
        }

        private sealed class Geometry
        {
            // Insets inside the painted faces of the original atlas, in 512px preview coordinates.
            private static readonly Rect[] PaintSamples =
            {
                new Rect(431f, 271f, 9f, 38f),
                new Rect(17f, 270f, 9f, 40f),
                new Rect(161f, 272f, 7f, 36f),
                new Rect(389f, 357f, 10f, 38f),
            };

            private Rect _paint;
            private float _atlasSize = 512f;
            private float _glyphLeft;
            private float _glyphRight;
            private float _rowBottom;
            private float _rowTop;

            private readonly List<Vector3> _vertices = new List<Vector3>();
            private readonly List<Vector2> _uv = new List<Vector2>();
            private readonly List<int> _triangles = new List<int>();

            public void AddRow(string name, float bottom, float top, float right, float left,
                float front = Front, float back = Back, Rect? paint = null, bool reverse = false, float atlasSize = 512f)
            {
                string[] rows;
                using (var stream = typeof(HotelSign).Assembly.GetManifestResourceStream("HotelSign." + name))
                using (var reader = new StreamReader(stream))
                    rows = reader.ReadToEnd().Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);

                int height = rows.Length;
                int width = rows[0].Length;
                float textWidth = Mathf.Min(left - right, (top - bottom) * width / height);
                float start = (left + right + textWidth) * 0.5f;
                _atlasSize = atlasSize;
                float StepX(int x) => reverse ? left + right - start + textWidth * x / width : start - textWidth * x / width;
                Vector3 outward = reverse ? Vector3.left : Vector3.right;
                Vector3 leftEdge = reverse ? Vector3.back : Vector3.forward;
                float StepY(int y) => Mathf.Lerp(top, bottom, (float)y / height);
                bool Filled(int x, int y) => x >= 0 && x < width && y >= 0 && y < height && rows[y][x] == '#';
                Vector3 Point(float depth, int x, int y) => new Vector3(depth, StepY(y), StepX(x));

                // Map each Cyrillic glyph to a clean patch of red paint rather than
                // projecting the entire Latin word and its background onto the new shapes.
                var occupied = new bool[width];
                for (int x = 0; x < width; x++)
                    for (int y = 0; y < height && !occupied[x]; y++)
                        occupied[x] = Filled(x, y);

                int glyph = 0;
                for (int startColumn = 0; startColumn < width;)
                {
                    if (!occupied[startColumn])
                    {
                        startColumn++;
                        continue;
                    }

                    int endColumn = startColumn + 1;
                    while (endColumn < width && occupied[endColumn])
                        endColumn++;
                    _paint = paint ?? PaintSamples[glyph++ % PaintSamples.Length];
                    _glyphLeft = StepX(startColumn);
                    _glyphRight = StepX(endColumn);
                    _rowBottom = bottom;
                    _rowTop = top;

                    AddGlyph(startColumn, endColumn);
                    startColumn = endColumn;
                }

                void AddGlyph(int first, int last)
                {
                    for (int y = 0; y < height; y++)
                    {
                        for (int x = first; x < last; x++)
                        {
                            if (!Filled(x, y))
                                continue;

                            if (!Filled(x - 1, y))
                            {
                                int end = x + 1;
                                while (Filled(end, y))
                                    end++;
                                Quad(Point(front, x, y), Point(front, x, y + 1), Point(front, end, y + 1), Point(front, end, y), outward);
                                Quad(Point(back, x, y), Point(back, x, y + 1), Point(back, end, y + 1), Point(back, end, y), -outward);
                                Side(x, y, x, y + 1, leftEdge);
                            }

                            if (!Filled(x + 1, y))
                                Side(x + 1, y, x + 1, y + 1, -leftEdge);
                            if (!Filled(x, y - 1))
                                Side(x, y, x + 1, y, Vector3.up);
                            if (!Filled(x, y + 1))
                                Side(x, y + 1, x + 1, y + 1, Vector3.down);
                        }
                    }
                }

                void Side(int x, int y, int endX, int endY, Vector3 normal)
                {
                    Quad(Point(front, x, y), Point(front, endX, endY),
                        Point(back, endX, endY), Point(back, x, y), normal);
                }
            }

            public void AddSmoothLetter(bool ring, float bottom, float top, float right, float left,
                float front, float back, Rect paint, bool reverse)
            {
                _atlasSize = 1024f;
                _paint = paint;
                _glyphLeft = left;
                _glyphRight = right;
                _rowBottom = bottom;
                _rowTop = top;

                var cross = new[]
                {
                    new Vector2(0.00f, 0.02f), new Vector2(0.24f, 0.02f), new Vector2(0.50f, 0.33f),
                    new Vector2(0.76f, 0.02f), new Vector2(1.00f, 0.02f), new Vector2(0.66f, 0.50f),
                    new Vector2(1.00f, 0.98f), new Vector2(0.76f, 0.98f), new Vector2(0.50f, 0.67f),
                    new Vector2(0.24f, 0.98f), new Vector2(0.00f, 0.98f), new Vector2(0.34f, 0.50f),
                };

                Vector3 Face(float depth, Vector2 uv) => new Vector3(depth,
                    Mathf.Lerp(bottom, top, uv.y), Mathf.Lerp(left, right, reverse ? 1f - uv.x : uv.x));
                Vector3 outward = reverse ? Vector3.left : Vector3.right;
                int sides = ring ? 64 : cross.Length;
                for (int i = 0; i < sides; i++)
                {
                    int next = (i + 1) % sides;
                    Vector2 a = ring ? Ellipse(i, 0.49f, 0.49f) : cross[i];
                    Vector2 b = ring ? Ellipse(next, 0.49f, 0.49f) : cross[next];
                    Vector2 c = ring ? Ellipse(next, 0.30f, 0.30f) : new Vector2(0.5f, 0.5f);
                    Vector2 d = ring ? Ellipse(i, 0.30f, 0.30f) : c;
                    Quad(Face(front, a), Face(front, b), Face(front, c), Face(front, d), outward);
                    Quad(Face(back, a), Face(back, b), Face(back, c), Face(back, d), -outward);
                    Side(a, b);
                    if (ring)
                        Side(c, d);
                }

                Vector2 Ellipse(int i, float rx, float ry)
                {
                    float angle = 2f * Mathf.PI * i / sides;
                    return new Vector2(0.5f + rx * Mathf.Cos(angle), 0.5f + ry * Mathf.Sin(angle));
                }

                void Side(Vector2 a, Vector2 b)
                {
                    Vector3 p = Face(front, a);
                    Vector3 q = Face(front, b);
                    // The facing normal already changes with the mirrored glyph coordinates.
                    // Applying the mirror sign again turns the back-side walls inside out.
                    Vector3 n = Vector3.Cross(q - p, outward);
                    Quad(p, q, Face(back, b), Face(back, a), n);
                }
            }

            public void AddFrame(Vector3 a, Vector3 b, Rect paint)
            {
                _atlasSize = 1024f;
                _paint = paint;
                _glyphLeft = b.z;
                _glyphRight = a.z;
                _rowBottom = a.y;
                _rowTop = b.y;

                const float border = 0.18f;
                const float corner = 0.13f;
                var outer = Outline(a.y, b.y, a.z, b.z, corner);
                var inner = Outline(a.y + border, b.y - border, a.z + border, b.z - border, 0.02f);
                var center = new Vector2((a.y + b.y) * 0.5f, (a.z + b.z) * 0.5f);
                for (int i = 0; i < outer.Length; i++)
                {
                    int next = (i + 1) % outer.Length;
                    Vector2 edge = (outer[i] + outer[next]) * 0.5f - center;
                    var normal = new Vector3(0f, edge.x, edge.y);
                    Quad(Point(a.x, outer[i]), Point(a.x, outer[next]),
                        Point(b.x, outer[next]), Point(b.x, outer[i]), normal);
                    Quad(Point(a.x, outer[i]), Point(a.x, outer[next]),
                        Point(a.x, inner[next]), Point(a.x, inner[i]), Vector3.left);
                    Quad(Point(b.x, outer[i]), Point(b.x, outer[next]),
                        Point(b.x, inner[next]), Point(b.x, inner[i]), Vector3.right);
                    Quad(Point(a.x, inner[i]), Point(a.x, inner[next]),
                        Point(b.x, inner[next]), Point(b.x, inner[i]), -normal);
                }

                Vector3 Point(float x, Vector2 yz) => new Vector3(x, yz.x, yz.y - (yz.x - 56.41f) * 0.025f);

                Vector2[] Outline(float bottom, float top, float left, float right, float cut)
                {
                    return new[]
                    {
                        new Vector2(bottom, left + cut), new Vector2(bottom, right - cut),
                        new Vector2(bottom + cut, right), new Vector2(top - cut, right),
                        new Vector2(top, right - cut), new Vector2(top, left + cut),
                        new Vector2(top - cut, left), new Vector2(bottom + cut, left),
                    };
                }
            }

            public void AddBox(Vector3 a, Vector3 b, Rect paint, float bevel)
            {
                _atlasSize = 1024f;
                _paint = paint;
                _glyphLeft = b.z;
                _glyphRight = a.z;
                _rowBottom = a.y;
                _rowTop = b.y;

                var rim = new[]
                {
                    new Vector2(a.x, a.z + bevel), new Vector2(a.x + bevel, a.z),
                    new Vector2(b.x - bevel, a.z), new Vector2(b.x, a.z + bevel),
                    new Vector2(b.x, b.z - bevel), new Vector2(b.x - bevel, b.z),
                    new Vector2(a.x + bevel, b.z), new Vector2(a.x, b.z - bevel),
                };
                float Slope(float y) => (y - 56.41f) * -0.025f;
                Vector3 Point(Vector2 p, float y) => new Vector3(p.x, y, p.y + Slope(y));
                var center = new Vector2((a.x + b.x) * 0.5f, (a.z + b.z) * 0.5f);
                for (int i = 0; i < rim.Length; i++)
                {
                    var p = rim[i];
                    var q = rim[(i + 1) % rim.Length];
                    var midpoint = (p + q) * 0.5f - center;
                    Quad(Point(p, a.y), Point(q, a.y), Point(q, b.y), Point(p, b.y),
                        new Vector3(midpoint.x, 0f, midpoint.y));
                    Quad(Point(p, b.y), Point(q, b.y), Point(center, b.y), Point(center, b.y), Vector3.up);
                    Quad(Point(p, a.y), Point(q, a.y), Point(center, a.y), Point(center, a.y), Vector3.down);
                }
            }

            private void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 normal)
            {
                int i = _vertices.Count;
                foreach (var v in new[] { a, b, c, d })
                {
                    _vertices.Add(v);
                    float u = Mathf.InverseLerp(_glyphLeft, _glyphRight, v.z);
                    float t = Mathf.InverseLerp(_rowTop, _rowBottom, v.y);
                    _uv.Add(new Vector2((_paint.x + u * _paint.width) / _atlasSize,
                        1f - (_paint.y + t * _paint.height) / _atlasSize));
                }

                if (Vector3.Dot(Vector3.Cross(b - a, c - a), normal) < 0f)
                    _triangles.AddRange(new[] { i, i + 2, i + 1, i, i + 3, i + 2 });
                else
                    _triangles.AddRange(new[] { i, i + 1, i + 2, i, i + 2, i + 3 });
            }

            public Mesh Build()
            {
                var mesh = new Mesh { name = "RTLC Hotel Sign", indexFormat = IndexFormat.UInt32 };
                mesh.SetVertices(_vertices);
                mesh.SetUVs(0, _uv);
                mesh.SetTriangles(_triangles, 0);
                mesh.RecalculateNormals();
                return mesh;
            }
        }
    }
}
