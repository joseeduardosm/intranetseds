using System.Diagnostics;
using System.Net.Http;
using System.Windows.Forms;

namespace ClientSgi.Desktop;

public sealed class TrayApplicationContext : ApplicationContext
{
    private readonly NotifyIcon _notifyIcon;
    private readonly MainForm _mainForm;
    private readonly AppStateStore _stateStore;
    private readonly DesktopApiClient _apiClient;
    private readonly System.Windows.Forms.Timer _pollTimer;
    private readonly ToolStripMenuItem _statusItem;
    private readonly ToolStripMenuItem _autoStartItem;
    private readonly Logger _logger;
    private readonly AutoStartManager _autoStartManager;
    private readonly Queue<DesktopNotification> _notificationQueue = new();
    private AppState _state;
    private NotificationPopupForm? _activePopup;
    private bool _polling;

    public TrayApplicationContext()
    {
        _logger = new Logger();
        _autoStartManager = new AutoStartManager();
        _stateStore = new AppStateStore();
        _state = _stateStore.Load();
        _apiClient = new DesktopApiClient(new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(15),
        })
        {
            BaseUrl = _state.BaseUrl,
            Token = _state.Token,
        };

        _mainForm = new MainForm();
        _mainForm.FormClosing += MainForm_FormClosing;
        _mainForm.SetFooter($"Log local: {_logger.LogPath}");

        _statusItem = new ToolStripMenuItem("Offline");
        _autoStartItem = new ToolStripMenuItem("Iniciar com o Windows")
        {
            Checked = _autoStartManager.IsEnabled(),
            CheckOnClick = true,
        };
        _autoStartItem.Click += AutoStartItem_Click;

        _notifyIcon = new NotifyIcon
        {
            Visible = true,
            Text = "Client SGI",
            Icon = LoadTrayIcon(),
            ContextMenuStrip = BuildMenu(),
        };
        _notifyIcon.DoubleClick += (_, _) => ShowMainWindow();

        _pollTimer = new System.Windows.Forms.Timer
        {
            Interval = 30000,
        };
        _pollTimer.Tick += async (_, _) => await PollNotificationsAsync();

        if (!string.IsNullOrWhiteSpace(_state.Token))
        {
            _logger.Info("Aplicação iniciada com sessão restaurada.");
            SetStatus("Sessão restaurada");
            _pollTimer.Start();
            _ = PollNotificationsAsync();
            return;
        }

        if (!string.IsNullOrWhiteSpace(_state.Username) && !string.IsNullOrWhiteSpace(_state.Password))
        {
            _logger.Info("Aplicação iniciada sem token, tentando reautenticação automática.");
            _ = TryAutoLoginAsync();
            return;
        }

        if (string.IsNullOrWhiteSpace(_state.Token))
        {
            _logger.Info("Aplicação iniciada sem sessão.");
            PromptLogin();
        }
    }

    private ContextMenuStrip BuildMenu()
    {
        var menu = new ContextMenuStrip();
        var openItem = new ToolStripMenuItem("Abrir");
        openItem.Click += (_, _) => ShowMainWindow();

        var loginItem = new ToolStripMenuItem("Login");
        loginItem.Click += (_, _) => PromptLogin();

        var refreshItem = new ToolStripMenuItem("Recarregar");
        refreshItem.Click += async (_, _) => await PollNotificationsAsync();

        var logoutItem = new ToolStripMenuItem("Sair da sessão");
        logoutItem.Click += async (_, _) => await LogoutAsync();

        var exitItem = new ToolStripMenuItem("Fechar");
        exitItem.Click += async (_, _) =>
        {
            await LogoutAsync(clearOnlyIfMissing: false, remoteLogout: false);
            _notifyIcon.Visible = false;
            ExitThread();
        };

        menu.Items.Add(openItem);
        menu.Items.Add(refreshItem);
        menu.Items.Add(loginItem);
        menu.Items.Add(_autoStartItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(_statusItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(logoutItem);
        menu.Items.Add(exitItem);
        return menu;
    }

    private Icon LoadTrayIcon()
    {
        try
        {
            var iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "clientsgi.ico");
            if (File.Exists(iconPath))
            {
                return new Icon(iconPath);
            }
        }
        catch
        {
            // Fallback silencioso para o ícone padrão.
        }

        return SystemIcons.Information;
    }

    private void AutoStartItem_Click(object? sender, EventArgs e)
    {
        try
        {
            _autoStartManager.SetEnabled(_autoStartItem.Checked);
            _logger.Info($"Inicialização automática alterada para: {_autoStartItem.Checked}");
            SetStatus(_autoStartItem.Checked ? "Inicialização automática ativada" : "Inicialização automática desativada");
        }
        catch (Exception ex)
        {
            _autoStartItem.Checked = !_autoStartItem.Checked;
            _logger.Error($"Falha ao configurar inicialização automática: {ex.Message}");
            MessageBox.Show(
                $"Falha ao configurar inicialização automática: {ex.Message}",
                "Client SGI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }
    }

    private void MainForm_FormClosing(object? sender, FormClosingEventArgs e)
    {
        e.Cancel = true;
        _mainForm.Hide();
        SetStatus("Janela principal recolhida para a bandeja.");
    }

    private void ShowMainWindow()
    {
        _mainForm.Show();
        _mainForm.WindowState = FormWindowState.Normal;
        _mainForm.BringToFront();
    }

    private void SetStatus(string status)
    {
        _statusItem.Text = status;
        _mainForm.AppendStatus(status);
        _logger.Info(status);
    }

    private void PromptLogin()
    {
        using var dialog = new LoginForm(_state.BaseUrl, _state.Username, _state.Password);
        if (dialog.ShowDialog() != DialogResult.OK)
        {
            return;
        }

        try
        {
            var loginResponse = PerformLoginAsync(dialog.BaseUrl, dialog.Username, dialog.Password, CancellationToken.None)
                .GetAwaiter()
                .GetResult();
            SetStatus($"Login realizado para {loginResponse.User.Full_Name}");
        }
        catch (Exception ex)
        {
            _logger.Error($"Falha no login: {ex}");
            MessageBox.Show(
                $"Falha no login: {ex.Message}",
                "Client SGI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private async Task<LoginResponse> PerformLoginAsync(string baseUrl, string username, string password, CancellationToken cancellationToken)
    {
        _apiClient.BaseUrl = baseUrl.Trim();
        var loginResponse = await _apiClient.LoginAsync(username, password, cancellationToken);

        _state.BaseUrl = baseUrl.Trim();
        _state.Username = username.Trim();
        _state.Password = password;
        _state.Token = loginResponse.Token;
        _apiClient.BaseUrl = _state.BaseUrl;
        _apiClient.Token = loginResponse.Token;
        _stateStore.Save(_state);

        if (!_autoStartItem.Checked)
        {
            _autoStartItem.Checked = true;
            _autoStartManager.SetEnabled(true);
            _logger.Info("Inicialização automática ativada por padrão após o primeiro login.");
        }

        _pollTimer.Start();
        await PollNotificationsAsync();
        return loginResponse;
    }

    private async Task TryAutoLoginAsync()
    {
        try
        {
            SetStatus("Tentando reautenticar automaticamente...");
            var loginResponse = await PerformLoginAsync(_state.BaseUrl, _state.Username, _state.Password, CancellationToken.None);
            SetStatus($"Sessão restaurada para {loginResponse.User.Full_Name}");
        }
        catch (Exception ex)
        {
            _logger.Error($"Falha na reautenticação automática: {ex}");
            _state.Token = string.Empty;
            _stateStore.Save(_state);
            SetStatus("Falha na reautenticação automática. Login manual necessário.");
            PromptLogin();
        }
    }

    private async Task LogoutAsync(bool clearOnlyIfMissing = false, bool remoteLogout = true)
    {
        try
        {
            if (remoteLogout && !string.IsNullOrWhiteSpace(_apiClient.Token))
            {
                await _apiClient.LogoutAsync(CancellationToken.None);
            }
        }
        catch
        {
            // Logout remoto não deve impedir a limpeza local.
            _logger.Error("Falha no logout remoto. A limpeza local continuará.");
        }

        if (!clearOnlyIfMissing || string.IsNullOrWhiteSpace(_state.Token))
        {
            _state.Token = string.Empty;
            _apiClient.Token = string.Empty;
            _stateStore.Save(_state);
        }

        _pollTimer.Stop();
        SetStatus("Sessão encerrada");
    }

    private async Task PollNotificationsAsync()
    {
        if (_polling || string.IsNullOrWhiteSpace(_apiClient.Token))
        {
            return;
        }

        _polling = true;
        try
        {
            var notifications = await _apiClient.GetNotificationsAsync(_state.SinceId, CancellationToken.None);
            if (notifications.Count == 0)
            {
                _statusItem.Text = "Conectado";
                return;
            }

            foreach (var notification in notifications.OrderBy(item => item.Id))
            {
                _state.SinceId = Math.Max(_state.SinceId, notification.Id);
                _stateStore.Save(_state);
                _logger.Info($"Notificação recebida: {notification.Id} - {notification.Title}");
                await _apiClient.MarkDisplayedAsync(notification.Id, CancellationToken.None);
                _mainForm.AppendStatus($"[{notification.Source_App}] {notification.Title} - {notification.Body_Short}");
                EnqueueNotification(notification);
            }

            _statusItem.Text = "Conectado";
        }
        catch (Exception ex)
        {
            _logger.Error($"Falha no polling: {ex}");
            SetStatus($"Offline ou erro: {ex.Message}");
        }
        finally
        {
            _polling = false;
        }
    }

    private void EnqueueNotification(DesktopNotification notification)
    {
        _notificationQueue.Enqueue(notification);
        ShowNextNotificationPopup();
    }

    private void ShowNextNotificationPopup()
    {
        if (_activePopup is not null || _notificationQueue.Count == 0)
        {
            return;
        }

        var notification = _notificationQueue.Dequeue();
        var popup = new NotificationPopupForm(notification);
        popup.OpenRequested += async (_, _) => await OpenNotificationAsync(notification);
        popup.DismissRequested += (_, _) =>
        {
            _mainForm.AppendStatus($"Notificação {notification.Id} fechada sem abrir.");
            _logger.Info($"Notificação {notification.Id} dispensada pelo usuário.");
        };
        popup.FormClosed += (_, _) =>
        {
            _activePopup = null;
            ShowNextNotificationPopup();
        };
        _activePopup = popup;
        popup.Show();
    }

    private async Task OpenNotificationAsync(DesktopNotification notification)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = notification.Target_Url,
                UseShellExecute = true,
            });
            await _apiClient.MarkReadAsync(notification.Id, CancellationToken.None);
            _mainForm.AppendStatus($"Notificação {notification.Id} aberta no navegador.");
            _logger.Info($"Notificação {notification.Id} aberta no navegador.");
        }
        catch (Exception ex)
        {
            _logger.Error($"Falha ao abrir notificação: {ex}");
            MessageBox.Show(
                $"Falha ao abrir a notificação: {ex.Message}",
                "Client SGI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }
    }
}
