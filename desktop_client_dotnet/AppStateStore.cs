using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace ClientSgi.Desktop;

public sealed class AppStateStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    private readonly string _statePath;

    public AppStateStore()
    {
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        var directory = Path.Combine(appData, "ClientSGI");
        Directory.CreateDirectory(directory);
        _statePath = Path.Combine(directory, "state.json");
    }

    public AppState Load()
    {
        if (!File.Exists(_statePath))
        {
            return new AppState();
        }

        var json = File.ReadAllText(_statePath, Encoding.UTF8);
        var state = JsonSerializer.Deserialize<AppState>(json, JsonOptions) ?? new AppState();
        if (!string.IsNullOrWhiteSpace(state.Token))
        {
            state.Token = Unprotect(state.Token);
        }
        if (!string.IsNullOrWhiteSpace(state.Password))
        {
            state.Password = Unprotect(state.Password);
        }
        return state;
    }

    public void Save(AppState state)
    {
        var payload = new AppState
        {
            BaseUrl = state.BaseUrl,
            Token = string.IsNullOrWhiteSpace(state.Token) ? string.Empty : Protect(state.Token),
            Username = state.Username,
            Password = string.IsNullOrWhiteSpace(state.Password) ? string.Empty : Protect(state.Password),
            SinceId = state.SinceId,
        };

        File.WriteAllText(_statePath, JsonSerializer.Serialize(payload, JsonOptions), Encoding.UTF8);
    }

    private static string Protect(string plainText)
    {
        var bytes = Encoding.UTF8.GetBytes(plainText);
        var protectedBytes = ProtectedData.Protect(bytes, null, DataProtectionScope.CurrentUser);
        return Convert.ToBase64String(protectedBytes);
    }

    private static string Unprotect(string cipherText)
    {
        try
        {
            var bytes = Convert.FromBase64String(cipherText);
            var unprotectedBytes = ProtectedData.Unprotect(bytes, null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(unprotectedBytes);
        }
        catch
        {
            return string.Empty;
        }
    }
}
