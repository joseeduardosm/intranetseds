using System.Text.Json.Serialization;

namespace ClientSgi.Desktop;

public sealed class LoginResponse
{
    [JsonPropertyName("token")]
    public string Token { get; set; } = string.Empty;

    [JsonPropertyName("token_type")]
    public string Token_Type { get; set; } = "Bearer";

    [JsonPropertyName("expires_at")]
    public string Expires_At { get; set; } = string.Empty;

    [JsonPropertyName("user")]
    public LoginUser User { get; set; } = new();
}

public sealed class LoginUser
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("username")]
    public string Username { get; set; } = string.Empty;

    [JsonPropertyName("full_name")]
    public string Full_Name { get; set; } = string.Empty;

    [JsonPropertyName("email")]
    public string Email { get; set; } = string.Empty;
}

public sealed class NotificationEnvelope
{
    [JsonPropertyName("results")]
    public List<DesktopNotification> Results { get; set; } = [];
}

public sealed class DesktopNotification
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("body_short")]
    public string Body_Short { get; set; } = string.Empty;

    [JsonPropertyName("target_url")]
    public string Target_Url { get; set; } = string.Empty;

    [JsonPropertyName("source_app")]
    public string Source_App { get; set; } = string.Empty;

    [JsonPropertyName("event_type")]
    public string Event_Type { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public string Created_At { get; set; } = string.Empty;

    [JsonPropertyName("read_at")]
    public string? Read_At { get; set; }

    [JsonPropertyName("displayed_at")]
    public string? Displayed_At { get; set; }
}

public sealed class AppState
{
    public string BaseUrl { get; set; } = "http://sgi.seds.sp.gov.br";
    public string Token { get; set; } = string.Empty;
    public string Username { get; set; } = string.Empty;
    public string Password { get; set; } = string.Empty;
    public int SinceId { get; set; }
}
