# VoiceSync Umbraco Integration

Bu eklenti, Umbraco CMS üzerindeki içerikleriniz yayınlandığında FastAPI tabanlı ses klonlama servisimiz (VoiceSync) ile konuşarak yazılarınızı seslendirir. Ses üretimi asenkron olarak arka planda yürütülür ve tamamlandığında içerik otomatik olarak yeniden yayınlanır.

## Dependency Injection (DI) Kaydı

Eklentiyi Umbraco projenize entegre etmek için `Program.cs` (veya .NET 6 öncesi projeler için `Startup.cs`) dosyasında bağımlılıkları kaydetmeniz gerekir.

Aşağıdaki satırları `Program.cs` dosyanıza ekleyin:

```csharp
using Umbraco.Cms.Core.Notifications;
using Umbraco.Plugin.VoiceSync;

// 1. HttpClient factory'yi ekleyin (zaten ekli değilse)
builder.Services.AddHttpClient();

// 2. Notification handler kaydı (İçerik yayınlandığında tetiklenir)
builder.Services.AddNotificationHandler<ContentPublishedNotification, VoiceSyncHandler>();

// 3. Background Service / Hosted Service kaydı (Arka planda durum sorgular)
builder.Services.AddHostedService<VoiceSyncPoller>();
```

## Yapılandırma (appsettings.json)

FastAPI backend API adresinizi ve anahtarınızı tanımlamak için aşağıdaki bloğu `appsettings.json` dosyanıza ekleyin:

```json
{
  "VoiceSync": {
    "ApiUrl": "http://localhost:8000",
    "ApiKey": "YOUR_SECRET_API_KEY",
    "VoiceId": "default"
  }
}
```

## Umbraco Content Type (Document Type) Özellikleri

Eklentinin çalışabilmesi için seslendirilmesini istediğiniz Document Type üzerinde aşağıdaki **3 özelliğin** (Property) tam olarak aynı takma adlarla (alias) tanımlanmış olması gerekmektedir:

1. **bodyText** (Rich Text Editor veya Textstring) - Okunacak ana içerik alanı.
2. **voiceSyncTaskId** (Textstring / Readonly) - Backend üzerinde çalışan işin ID'sini saklar.
3. **voiceSyncAudioUrl** (Textstring / Readonly) - Üretilen MP3 ses dosyasının tam URL'sini saklar.
