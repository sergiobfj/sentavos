# Exporta os pixels da geometria original; nao redesenha a marca do aplicativo.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
public static class SentavosIcons {
    public static void Export(string source, string target) {
        using (var input = new Bitmap(source))
        using (var output = new Bitmap(input.Width, input.Height, PixelFormat.Format32bppArgb)) {
            var background = input.GetPixel(0, 0);
            int peak = background.R;
            int[] counts = new int[256];
            for (int y = 0; y < input.Height; y++)
                for (int x = 0; x < input.Width; x++) {
                    int red = input.GetPixel(x, y).R;
                    if (red > background.R + 50) counts[red]++;
                }
            for (int red = 0; red < counts.Length; red++)
                if (counts[red] > counts[peak]) peak = red;
            if (peak <= background.R) throw new Exception("Asset sem simbolo distinguivel.");
            for (int y = 0; y < input.Height; y++) for (int x = 0; x < input.Width; x++) {
                var p = input.GetPixel(x, y);
                double coverage = Math.Max(0, Math.Min(1, (p.R - background.R) / (double)(peak - background.R)));
                output.SetPixel(x, y, Color.FromArgb(p.A,
                    (int)Math.Round(16 + 239 * coverage),
                    (int)Math.Round(19 + 236 * coverage),
                    (int)Math.Round(25 + 230 * coverage)));
            }
            output.Save(target, ImageFormat.Png);
        }
    }
    public static byte[] Resize(string source, int size) {
        using (var input = new Bitmap(source))
        using (var output = new Bitmap(size, size))
        using (var graphics = Graphics.FromImage(output))
        using (var stream = new MemoryStream()) {
            graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
            graphics.DrawImage(input, 0, 0, size, size);
            output.Save(stream, ImageFormat.Png);
            return stream.ToArray();
        }
    }
    public static void Favicon(string source, string png, string ico) {
        File.WriteAllBytes(png, Resize(source, 32));
        int[] sizes = {16, 32, 48};
        byte[][] images = { Resize(source, 16), Resize(source, 32), Resize(source, 48) };
        using (var writer = new BinaryWriter(File.Create(ico))) {
            writer.Write((short)0); writer.Write((short)1); writer.Write((short)3);
            int offset = 6 + 16 * 3;
            for (int i = 0; i < 3; i++) {
                writer.Write((byte)sizes[i]); writer.Write((byte)sizes[i]); writer.Write((short)0);
                writer.Write((short)1); writer.Write((short)32); writer.Write(images[i].Length);
                writer.Write(offset); offset += images[i].Length;
            }
            foreach (var bytes in images) writer.Write(bytes);
        }
    }
}
'@
$iconsRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'frontend/public'
foreach ($name in @('icon-192', 'icon-512', 'icon-maskable-512', 'apple-touch-icon')) {
    [SentavosIcons]::Export((Join-Path $iconsRoot "$name.png"), (Join-Path $iconsRoot "$name-white-v1.png"))
}
[SentavosIcons]::Favicon((Join-Path $iconsRoot 'icon-512-white-v1.png'), (Join-Path $iconsRoot 'favicon-white-v1.png'), (Join-Path $iconsRoot 'favicon-white-v1.ico'))
