using System.Runtime.InteropServices;

namespace Om0rxAgent;

public static class TrayIconFactory
{
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool DestroyIcon(IntPtr hIcon);

    public static Icon Create(ComponentStatus status)
    {
        using var bitmap = new Bitmap(32, 32);
        using (var g = Graphics.FromImage(bitmap))
        {
            g.Clear(Color.Transparent);
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;

            var color = status switch
            {
                ComponentStatus.Ok => Color.FromArgb(34, 163, 84),
                ComponentStatus.Busy => Color.FromArgb(43, 126, 214),
                ComponentStatus.Warning => Color.FromArgb(230, 143, 31),
                ComponentStatus.Error => Color.FromArgb(210, 56, 56),
                ComponentStatus.Off => Color.FromArgb(110, 118, 129),
                _ => Color.FromArgb(110, 118, 129),
            };

            using var fill = new SolidBrush(color);
            using var border = new Pen(Color.FromArgb(35, 35, 35), 2);
            g.FillEllipse(fill, 3, 3, 26, 26);
            g.DrawEllipse(border, 3, 3, 26, 26);
            using var font = new Font("Segoe UI", 11, FontStyle.Bold, GraphicsUnit.Pixel);
            var text = status == ComponentStatus.Ok ? "O" : "!";
            var size = g.MeasureString(text, font);
            using var textBrush = new SolidBrush(Color.White);
            g.DrawString(text, font, textBrush, (32 - size.Width) / 2, (32 - size.Height) / 2 - 1);
        }

        var handle = bitmap.GetHicon();
        try
        {
            return (Icon)Icon.FromHandle(handle).Clone();
        }
        finally
        {
            DestroyIcon(handle);
        }
    }
}
