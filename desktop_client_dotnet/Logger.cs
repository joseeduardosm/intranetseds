using System.Text;

namespace ClientSgi.Desktop;

public sealed class Logger
{
    private readonly string _logPath;
    private readonly object _sync = new();

    public Logger()
    {
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        var directory = Path.Combine(appData, "ClientSGI");
        Directory.CreateDirectory(directory);
        _logPath = Path.Combine(directory, "clientsgi.log");
    }

    public void Info(string message) => Write("INFO", message);
    public void Error(string message) => Write("ERROR", message);

    public string LogPath => _logPath;

    private void Write(string level, string message)
    {
        var line = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] [{level}] {message}{Environment.NewLine}";
        lock (_sync)
        {
            File.AppendAllText(_logPath, line, Encoding.UTF8);
        }
    }
}

