using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace ClientSgi.Desktop;

public sealed class DesktopApiClient
{
    private readonly HttpClient _httpClient;
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    public DesktopApiClient(HttpClient httpClient)
    {
        _httpClient = httpClient;
    }

    public string BaseUrl { get; set; } = "http://sgi.seds.sp.gov.br";

    public string Token { get; set; } = string.Empty;

    private HttpRequestMessage CreateRequest(HttpMethod method, string path)
    {
        var request = new HttpRequestMessage(method, $"{BaseUrl.TrimEnd('/')}{path}");
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (!string.IsNullOrWhiteSpace(Token))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Token);
        }
        return request;
    }

    public async Task<LoginResponse> LoginAsync(string username, string password, CancellationToken cancellationToken)
    {
        using var request = CreateRequest(HttpMethod.Post, "/api/desktop/auth/login/");
        var requestBody = JsonSerializer.Serialize(new
        {
            username = username.Trim(),
            password = password,
        });
        request.Content = new StringContent(requestBody, Encoding.UTF8, "application/json");

        using var response = await _httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new HttpRequestException(
                $"Response status code does not indicate success: {(int)response.StatusCode} ({response.ReasonPhrase}). Body: {errorBody}");
        }
        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        var loginResponse = JsonSerializer.Deserialize<LoginResponse>(responseBody, _jsonOptions);
        if (loginResponse is null || string.IsNullOrWhiteSpace(loginResponse.Token))
        {
            throw new InvalidOperationException("A API retornou uma resposta de login inválida.");
        }
        Token = loginResponse.Token;
        return loginResponse;
    }

    public async Task LogoutAsync(CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(Token))
        {
            return;
        }

        using var request = CreateRequest(HttpMethod.Post, "/api/desktop/auth/logout/");
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        Token = string.Empty;
    }

    public async Task<IReadOnlyList<DesktopNotification>> GetNotificationsAsync(int sinceId, CancellationToken cancellationToken)
    {
        var suffix = sinceId > 0 ? $"?since_id={sinceId}" : string.Empty;
        using var request = CreateRequest(HttpMethod.Get, $"/api/desktop/notificacoes/{suffix}");
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        var envelope = JsonSerializer.Deserialize<NotificationEnvelope>(responseBody, _jsonOptions);
        return envelope?.Results ?? [];
    }

    public Task MarkDisplayedAsync(int notificationId, CancellationToken cancellationToken) =>
        PostWithoutPayloadAsync($"/api/desktop/notificacoes/{notificationId}/marcar-exibida/", cancellationToken);

    public Task MarkReadAsync(int notificationId, CancellationToken cancellationToken) =>
        PostWithoutPayloadAsync($"/api/desktop/notificacoes/{notificationId}/marcar-lida/", cancellationToken);

    private async Task PostWithoutPayloadAsync(string path, CancellationToken cancellationToken)
    {
        using var request = CreateRequest(HttpMethod.Post, path);
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }
}
