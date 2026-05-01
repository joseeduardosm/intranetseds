using System.Windows.Forms;

namespace ClientSgi.Desktop;

public sealed class NotificationPopupForm : Form
{
    private readonly Button _openButton;
    private readonly Button _closeButton;

    public NotificationPopupForm(DesktopNotification notification)
    {
        Notification = notification;

        Text = "Notificações SGI";
        Width = 400;
        Height = 290;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        ShowInTaskbar = false;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.Manual;
        TopMost = true;

        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
            Padding = new Padding(14),
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));

        var contentPanel = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            AutoScroll = true,
            AutoSize = false,
            Margin = new Padding(0),
            Padding = new Padding(0),
        };

        AddLine(contentPanel, notification.Title, bold: true, topPadding: 0);
        foreach (var line in notification.Body_Short.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            AddLine(contentPanel, line, bold: false, topPadding: 6);
        }

        var buttonPanel = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
            AutoSize = true,
            WrapContents = false,
        };

        _openButton = new Button
        {
            Text = "Abrir",
            AutoSize = true,
            Padding = new Padding(10, 4, 10, 4),
        };
        _openButton.Click += (_, _) =>
        {
            OpenRequested?.Invoke(this, EventArgs.Empty);
            Close();
        };

        _closeButton = new Button
        {
            Text = "Fechar",
            AutoSize = true,
            Padding = new Padding(10, 4, 10, 4),
        };
        _closeButton.Click += (_, _) =>
        {
            DismissRequested?.Invoke(this, EventArgs.Empty);
            Close();
        };

        buttonPanel.Controls.Add(_openButton);
        buttonPanel.Controls.Add(_closeButton);

        layout.Controls.Add(contentPanel, 0, 0);
        layout.Controls.Add(buttonPanel, 0, 1);

        Controls.Add(layout);
    }

    public DesktopNotification Notification { get; }

    public event EventHandler? OpenRequested;

    public event EventHandler? DismissRequested;

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        PositionBottomRight();
    }

    private void PositionBottomRight()
    {
        var area = Screen.PrimaryScreen?.WorkingArea ?? Screen.FromControl(this).WorkingArea;
        Location = new Point(area.Right - Width - 16, area.Bottom - Height - 16);
    }

    private static void AddLine(FlowLayoutPanel panel, string text, bool bold, int topPadding)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        var label = new Label
        {
            AutoSize = true,
            MaximumSize = new Size(340, 0),
            Margin = new Padding(0, topPadding, 0, 0),
            Font = bold ? new Font("Segoe UI", 10.5F, FontStyle.Bold) : new Font("Segoe UI", 10F),
            Text = text,
        };
        panel.Controls.Add(label);
    }
}
