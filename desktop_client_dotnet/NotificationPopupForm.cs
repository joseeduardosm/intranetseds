using System.Windows.Forms;

namespace ClientSgi.Desktop;

public sealed class NotificationPopupForm : Form
{
    private readonly Label _titleLabel;
    private readonly Label _messageLabel;
    private readonly Button _openButton;
    private readonly Button _closeButton;

    public NotificationPopupForm(DesktopNotification notification)
    {
        Notification = notification;

        Text = "Notificações SGI";
        Width = 360;
        Height = 250;
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
            RowCount = 3,
            Padding = new Padding(14),
        };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));

        _titleLabel = new Label
        {
            Dock = DockStyle.Top,
            AutoSize = true,
            Font = new Font("Segoe UI", 11F, FontStyle.Bold),
            Text = notification.Title,
            MaximumSize = new Size(320, 0),
        };

        _messageLabel = new Label
        {
            Dock = DockStyle.Fill,
            AutoSize = true,
            Font = new Font("Segoe UI", 10F),
            Text = notification.Body_Short,
            MaximumSize = new Size(320, 0),
            Padding = new Padding(0, 8, 0, 0),
        };

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

        layout.Controls.Add(_titleLabel, 0, 0);
        layout.Controls.Add(_messageLabel, 0, 1);
        layout.Controls.Add(buttonPanel, 0, 2);

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
}
