using System.Windows.Forms;

namespace ClientSgi.Desktop;

public sealed class LoginForm : Form
{
    private readonly TextBox _baseUrlInput;
    private readonly TextBox _usernameInput;
    private readonly TextBox _passwordInput;

    public LoginForm(string baseUrl, string username, string password)
    {
        Text = "Client SGI - Login";
        Width = 420;
        Height = 220;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;

        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 4,
            Padding = new Padding(12),
        };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        _baseUrlInput = new TextBox { Text = baseUrl, Dock = DockStyle.Fill };
        _usernameInput = new TextBox { Text = username, Dock = DockStyle.Fill };
        _passwordInput = new TextBox
        {
            Text = password,
            UseSystemPasswordChar = true,
            Dock = DockStyle.Fill,
        };

        layout.Controls.Add(new Label { Text = "Base URL", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 0);
        layout.Controls.Add(_baseUrlInput, 1, 0);
        layout.Controls.Add(new Label { Text = "Usuário", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 1);
        layout.Controls.Add(_usernameInput, 1, 1);
        layout.Controls.Add(new Label { Text = "Senha", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 2);
        layout.Controls.Add(_passwordInput, 1, 2);

        var submitButton = new Button
        {
            Text = "Entrar",
            Dock = DockStyle.Right,
            Width = 100,
        };
        submitButton.Click += (_, _) => DialogResult = DialogResult.OK;
        layout.Controls.Add(submitButton, 1, 3);

        AcceptButton = submitButton;
        Controls.Add(layout);
    }

    public string BaseUrl => _baseUrlInput.Text.Trim();
    public string Username => _usernameInput.Text.Trim();
    public string Password => _passwordInput.Text;
}
