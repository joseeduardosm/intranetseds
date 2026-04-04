using System.Text;
using System.Windows.Forms;

namespace ClientSgi.Desktop;

public sealed class MainForm : Form
{
    private readonly TextBox _statusBox;
    private readonly Label _footer;

    public MainForm()
    {
        Text = "Client SGI";
        Width = 700;
        Height = 420;
        StartPosition = FormStartPosition.CenterScreen;

        _statusBox = new TextBox
        {
            Multiline = true,
            ReadOnly = true,
            Dock = DockStyle.Fill,
            ScrollBars = ScrollBars.Vertical,
            Font = new Font("Segoe UI", 10F),
        };
        _footer = new Label
        {
            Dock = DockStyle.Bottom,
            Height = 28,
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(8, 0, 0, 0),
        };

        Controls.Add(_statusBox);
        Controls.Add(_footer);
    }

    public void AppendStatus(string line)
    {
        var content = new StringBuilder();
        if (!string.IsNullOrWhiteSpace(line))
        {
            content.AppendLine($"[{DateTime.Now:dd/MM/yyyy HH:mm:ss}] {line}");
        }
        if (!string.IsNullOrWhiteSpace(_statusBox.Text))
        {
            content.AppendLine(_statusBox.Text);
        }
        _statusBox.Text = content.ToString().Trim();
    }

    public void SetFooter(string text)
    {
        _footer.Text = text;
    }
}
