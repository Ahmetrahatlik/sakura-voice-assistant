// Sakura bildirim maskotu: ekranın sağ altında belirip el sallar, ses çalar, kaybolur.
// Kullanım: Sakura.exe done | ask | error | work   (Claude Code hook'ları çağırır; hook verisi stdin'den okunur)
//           Sakura.exe menu                 (Görünüm penceresini açar)
//           Sakura.exe                      (ana program: tepsi simgesi, mesaj izleyici, isteğe bağlı masaüstü arkadaşı)
//           Sakura.exe install | uninstall  (Uygulamalar listesine kayıt, kısayollar / tamamen kaldırma)
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static class Program
{
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] static extern bool AllowSetForegroundWindow(int pid);

    [STAThread]
    static void Main(string[] args)
    {
        string mode = args.Length > 0 ? args[0] : "host";
        if (mode == "pet") mode = "host";
        if (mode == "voicetest")
        {
            // Test: Sakura.exe voicetest çıktı.wav "metin" [ifade] → Luna'nın sesini dosyaya yazar
            File.WriteAllBytes(args[1], Voice.Synth(args.Length > 2 ? args[2] : "Merhaba~", args.Length > 3 ? args[3] : null, 100, 30));
            return;
        }
        if (mode == "export")
        {
            // Test için: Sakura.exe export çıktı.png hair=#rrggbb emote=nese ...  → boyanmış ilk kareyi kaydeder.
            var c = Config.Load();
            string em = null, prefix = "wave_";
            int fr = 0;
            foreach (var a in args.Skip(2))
            {
                var kv = a.Split('=');
                if (kv.Length != 2) continue;
                if (kv[0] == "emote") em = kv[1];
                else if (kv[0] == "look") c.Look = kv[1];
                else if (kv[0] == "prefix") prefix = kv[1];
                else if (kv[0] == "frame") int.TryParse(kv[1], out fr);
                else c.Colors[kv[0]] = kv[1];
            }
            var frames = new Sprites(c.Look, prefix, em).Render(c.Colors);
            frames[Math.Min(fr, frames.Count - 1)].Save(args[1], ImageFormat.Png);
            return;
        }
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        // Beklenmeyen bir hata olursa ekrana .NET hata penceresi açma; error.log'a yaz ve devam et.
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) => LogError(e.Exception);
        AppDomain.CurrentDomain.UnhandledException += (s, e) => LogError(e.ExceptionObject as Exception);
        if (mode == "menu")
        {
            // Uygulama penceresi ana programın içinde açılır; ön plana gelebilmesi için izin veriyoruz.
            Detached.EnsureRunning(Config.Load());
            AllowSetForegroundWindow(-1);
            var open = new Event { Mode = "open", Body = args.Length > 1 ? args[1] : "" };
            for (int i = 0; i < 25; i++) { if (PetForm.TrySend(open)) return; Thread.Sleep(200); }
            return;
        }
        if (mode == "install") { Installer.Install(); return; }
        if (mode == "desktest") { File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), Desk.Dump(), Encoding.UTF8); return; } // test: masaüstü simgeleri ve yerleri
        if (mode == "dekor" && args.Length >= 2) { File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), args[1] == "kur" ? Desk.Setup(args.Length > 2 && args[2] == "bos") : Desk.Restore(), Encoding.UTF8); return; } // çekim masaüstü: kur | geri
        if (mode == "simge" && args.Length >= 4) { Desk.PlaceSure(new Dictionary<string, Point> { { args[1], new Point(int.Parse(args[2]), int.Parse(args[3])) } }); return; } // simgeyi yerine koy: yol x y
        if (mode == "sahnetest" && args.Length >= 2) { PetForm.TrySend(new Event { Mode = "sahne", Body = args[1] }); return; } // test: klasör sahnesi
        if (mode == "vedatest") { PetForm.TrySend(new Event { Mode = "close" }); return; } // test: içeriden kapatır (veda animasyonuyla)
        if (mode == "perftest") { PetForm.TrySend(new Event { Mode = "perf" }); return; } // çizim hızı ölçümü → quiet.log
        if (mode == "animexport") { Anim.Export(args); return; }
        if (mode == "animtest" && args.Length >= 2) { PetForm.TrySend(new Event { Mode = "anim", Body = args[1] + (args.Length > 2 ? " " + args[2] : "") }); return; } // test: klibi ya da tetiği oynat ("ayna" ile ters)
        if (mode == "roamtest") { PetForm.TrySend(new Event { Mode = "roam" }); return; } // test: hemen gezintiye çıkar
        if (mode == "minitest") { PetForm.TrySend(new Event { Mode = "mini", Body = args.Length > 1 ? args[1] : "30" }); return; } // test: N sn mini (0 = bitir)
        if (mode == "weathertest" && args.Length >= 2) { PetForm.TrySend(new Event { Mode = "weather", Body = args[1] }); return; } // rain | snow | hot | clear
        if (mode == "helptest" && args.Length >= 3)
        {
            // test: Sakura'ya sor yapay zekâ çağrısı → dry.txt
            string err;
            var ans = Brain.Help(Config.Load(), args[1], args[2], out err);
            File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), ans ?? ("HATA: " + err), Encoding.UTF8);
            return;
        }
        if (mode == "asktest" && args.Length >= 2) { PetForm.TrySend(new Event { Mode = "ask", Body = args[1] }); return; } // test: verilen metinle Sakura'ya sor
        if (mode == "droptest" && args.Length >= 3) { PetForm.TrySend(new Event { Mode = "drop", Body = args[1] + "," + args[2] }); return; } // test: büstün alt ortası (x, y)'ye bırakılmış gibi
        if (mode == "perchtest" || mode == "sleeptest" || mode == "flingtest" || mode == "lovetest" || mode == "confettitest" || mode == "missedtest") { PetForm.TrySend(new Event { Mode = mode.Replace("test", "") }); return; } // test: pencereye oturma, uyuklama, fırlatma
        if (mode == "asktest")
        {
            // Test için: Sakura'nın beynine bir soru sorar, cevabı (ya da hatayı) dry.txt'ye yazar.
            string err;
            var sw = Stopwatch.StartNew();
            var ans = Brain.Ask(Config.Load(), "", new List<Brain.Msg> { new Brain.Msg { Role = "user", Text = args.Length > 1 ? args[1] : "Merhaba!" } }, out err);
            File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), (ans ?? "HATA: " + err) + Environment.NewLine + (int)sw.Elapsed.TotalSeconds + " sn", Encoding.UTF8);
            return;
        }
        if (mode == "studiotest")
        {
            // Test için: Stüdyo önerilerini ister, kaydedilenlerin başına ekler; sonucu dry.txt'ye yazar.
            string err;
            var sw = Stopwatch.StartNew();
            var old = Studio.Load();
            var got = Studio.Suggest(Config.Load(), old, out err);
            if (got != null) { old.InsertRange(0, got); Studio.Save(old); }
            File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), (got == null ? "HATA: " + err : got.Count + " öneri: " + string.Join(" | ", got.Select(p => p.title))) + Environment.NewLine + (int)sw.Elapsed.TotalSeconds + " sn", Encoding.UTF8);
            return;
        }
        if (mode == "reel")
        {
            // Test için: Sakura.exe reel <öneri sırası> <çıktı.mp4|.png> [t=saniye]  → kayıtlı öneriyi videoya (ya da tek kareye) çevirir.
            var posts = Studio.Load();
            int idx = 0;
            if (args.Length < 3 || !int.TryParse(args[1], out idx) || idx >= posts.Count) return;
            using (var r = new Reel(Config.Load(), posts[idx]))
            {
                string msg;
                if (args[2].EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                {
                    double t = 1;
                    foreach (var a in args.Skip(3)) if (a.StartsWith("t=")) double.TryParse(a.Substring(2), NumberStyles.Float, CultureInfo.InvariantCulture, out t);
                    using (var bmp = new Bitmap(Reel.W, Reel.H, PixelFormat.Format32bppArgb))
                    {
                        using (var g = Graphics.FromImage(bmp)) r.Draw(g, t);
                        using (var big = new Bitmap(Reel.W * 2, Reel.H * 2))
                        {
                            using (var g = Graphics.FromImage(big)) { g.InterpolationMode = InterpolationMode.NearestNeighbor; g.PixelOffsetMode = PixelOffsetMode.Half; g.DrawImage(bmp, 0, 0, big.Width, big.Height); }
                            big.Save(args[2], ImageFormat.Png);
                        }
                    }
                    msg = "kare: " + r.Duration.ToString("0.0", CultureInfo.InvariantCulture) + " sn";
                }
                else msg = r.Export(args[2], null) ?? ("video: " + r.Duration.ToString("0.0", CultureInfo.InvariantCulture) + " sn");
                File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), msg, Encoding.UTF8);
            }
            return;
        }
        if (mode == "watchtest")
        {
            // Test için: mesaj izleyicisinin bildirim kaydından okuduğu son varış zamanlarını dry.txt'ye yazar.
            var r = MessageWatch.Read();
            File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), r == null ? "okunamadi" : string.Join(Environment.NewLine, r.Select(kv => kv.Key + "=" + kv.Value)));
            return;
        }
        if (mode == "uninstall") { Installer.Uninstall(); return; }
        if (mode == "host")
        {
            // Claude'un içinden (hook, menü) başlatıldıysak Claude kapanınca biz de kapanırız: bağımsız olarak yeniden başla.
            if (Detached.InJob() && !args.Contains("--detached")) { Detached.Start(Application.ExecutablePath, "host --detached"); return; }
            using (var mutex = new Mutex(false, "SakuraPetSingleInstance"))
            {
                bool owned;
                try { owned = mutex.WaitOne(args.Contains("--wait") ? 5000 : 0); }
                catch (AbandonedMutexException) { owned = true; }
                if (!owned) return;
                try { Application.Run(new PetForm(Config.Load())); }
                finally { mutex.ReleaseMutex(); }
            }
            return;
        }
        if (mode == "show")
        {
            // Ayrık süreç: hazır olayı ekranda gösterir.
            bool created;
            using (new Mutex(true, "SakuraMascotSingleInstance", out created))
                if (created) Application.Run(new MascotForm(Event.Decode(args[1]), Config.Load()));
            return;
        }

        // Hook ya da izleyici çağrısı: olayı hazırla, hemen teslim et ve çık (hook beklemesin).
        var cfg = Config.Load();
        Detached.EnsureRunning(cfg);
        if (mode != "work" && (cfg.SnoozeUntil > DateTime.Now || (!PetForm.IsRunning() && Quiet.ShouldHide(cfg)))) return; // ana program açıksa tam ekranı o yönetir (bekletir)
        var ev = EventBuilder.Build(mode, args, ReadStdin(), cfg);
        if (ev == null) return;
        if (mode == "work") { PetForm.TrySend(ev); return; }
        if (args.Contains("--dry"))
        {
            // Test için: olayı göstermeden dry.txt'ye yazar.
            File.WriteAllText(Path.Combine(Config.Dir, "dry.txt"), string.Join(Environment.NewLine, new[] { ev.Mode, ev.Title, ev.Body, ev.Footer, ev.Emote, ev.Sound, ev.Prefix, ev.Click }), Encoding.UTF8);
            return;
        }
        for (int i = 0; i < 25; i++)
        {
            if (PetForm.TrySend(ev)) return;
            Thread.Sleep(200);
        }
        Process.Start(new ProcessStartInfo(Application.ExecutablePath, "show " + ev.Encode()) { UseShellExecute = false });
    }

    internal static void LogQuiet(string line)
    {
        try
        {
            string f = Path.Combine(Config.Dir, "quiet.log");
            if (File.Exists(f) && new FileInfo(f).Length > 200000) File.Delete(f);
            File.AppendAllText(f, DateTime.Now.ToString("s") + " " + line + Environment.NewLine);
        }
        catch { }
    }

    internal static void LogError(Exception ex)
    {
        try { File.AppendAllText(Path.Combine(Config.Dir, "error.log"), DateTime.Now.ToString("s") + " " + ex + Environment.NewLine); } catch { }
    }

    static string ReadStdin()
    {
        try
        {
            if (!Console.IsInputRedirected) return "";
            var t = Task.Run(() => new StreamReader(Console.OpenStandardInput(), Encoding.UTF8).ReadToEnd());
            return t.Wait(1500) ? t.Result : "";
        }
        catch { return ""; }
    }
}

class Config
{
    public static readonly string Dir = Path.GetDirectoryName(Application.ExecutablePath);
    static readonly string FilePath = Path.Combine(Dir, "config.ini");
    public static readonly string[] GroupKeys = { "hair", "eyes", "outfit", "ribbon" }; // grup 1..4

    public string Look = "klasik";
    public string Emote = "rastgele"; // "rastgele" ya da Emotes.Keys içinden biri
    public bool Muted;
    public bool Voice = true;              // Luna balonda konuşurken Undertale tarzı flüt sesi
    public int VoiceVol = 75;              // 0..100
    public DateTime SnoozeUntil = DateTime.MinValue;
    public int Scale = 1;
    public double Seconds = 5;
    public bool HideInGames = true, HideInFullscreen;
    public bool Pet, PetTopmost = true, PetSmall;
    public bool AnimOn = true;             // hareket katmanı (anims.json)
    // Mini (chibi) Sakura: köşede küçük oturan hâl (frames/mini). Her zaman / video izlerken / oyunda.
    public bool MiniAlways, MiniVideo = true, MiniGame;
    public int MiniDx = -1, MiniDy = -1;   // mini'nin ekranın sağ/alt kenarına uzaklığı (sürükleyince); -1 = köşe
    public int PetX = -1, PetY = -1;
    public string LastGreet = "";
    public string LastStretch = "";        // sabah gerinmesinin yapıldığı gün
    public bool Spotify = true;
    public int BreakMinutes = 50;          // 0 = mola hatırlatma kapalı
    public string City = "", CityLat = "", CityLon = "", LastWeather = "", LastSummary = "";
    public int Love = 60;                  // sevgi barı 0-100
    public long LoveTs;                    // sevginin en son güncellendiği an (ticks)
    public bool ScreenAware = true, SystemAlerts = true, AiComments = true;
    public string AiModel = "claude-opus-5-5";
    public string AiBackend = "max";       // "max": Claude Code (abonelik) üzerinden, "api": API anahtarıyla
    public bool PhoneOn, PhoneOnlyAway = true; // ntfy ile telefona bildirim
    public string NtfyTopic = "";
    public string LastTodoNoon = "", LastTodoEve = "", LastTodoParty = "";
    public string Birthday = "", LastSpecial = ""; // doğum günü "gg.aa"; LastSpecial: "yyyy-MM-dd anahtar anahtar" (bugün kutlananlar)
    public bool BirthdayAsked;
    public string HatFrom = "";            // bayram beresi takılmadan önceki görünüm (bayram bitince geri döner); boş = takılı değil
    public int LoveLevel = -1;             // son sevgi seviyesi (0 Küs .. 4 En iyi ev arkadaşı); -1 = henüz yok
    // Boş = orijinal renk, aksi halde "#rrggbb".
    public Dictionary<string, string> Colors = GroupKeys.ToDictionary(k => k, k => "");

    public static Config Load()
    {
        var c = new Config();
        if (!File.Exists(FilePath)) return c;
        foreach (var line in File.ReadAllLines(FilePath))
        {
            var kv = line.Split(new[] { '=' }, 2);
            if (kv.Length != 2) continue;
            string k = kv[0].Trim(), v = kv[1].Trim();
            if (k == "look") c.Look = v;
            else if (k == "emote") c.Emote = v;
            else if (k == "muted") c.Muted = v == "1";
            else if (k == "voice") c.Voice = v != "0";
            else if (k == "voice_vol") int.TryParse(v, out c.VoiceVol);
            else if (k == "snooze_until") { long t; if (long.TryParse(v, out t)) c.SnoozeUntil = new DateTime(t); }
            else if (k == "scale") int.TryParse(v, out c.Scale);
            else if (k == "seconds") double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out c.Seconds);
            else if (k == "hide_games") c.HideInGames = v == "1";
            else if (k == "hide_fullscreen") c.HideInFullscreen = v == "1";
            else if (k == "pet") c.Pet = v == "1";
            else if (k == "pet_topmost") c.PetTopmost = v == "1";
            else if (k == "pet_small") c.PetSmall = v == "1";
            else if (k == "anim") c.AnimOn = v != "0";
            else if (k == "mini_always") c.MiniAlways = v == "1";
            else if (k == "mini_video") c.MiniVideo = v != "0";
            else if (k == "mini_game") c.MiniGame = v == "1";
            else if (k == "mini_dx") int.TryParse(v, out c.MiniDx);
            else if (k == "mini_dy") int.TryParse(v, out c.MiniDy);
            else if (k == "pet_x") int.TryParse(v, out c.PetX);
            else if (k == "pet_y") int.TryParse(v, out c.PetY);
            else if (k == "last_greet") c.LastGreet = v;
            else if (k == "last_stretch") c.LastStretch = v;
            else if (k == "spotify") c.Spotify = v == "1";
            else if (k == "break_minutes") int.TryParse(v, out c.BreakMinutes);
            else if (k == "city") c.City = v;
            else if (k == "city_lat") c.CityLat = v;
            else if (k == "city_lon") c.CityLon = v;
            else if (k == "last_weather") c.LastWeather = v;
            else if (k == "last_summary") c.LastSummary = v;
            else if (k == "love") int.TryParse(v, out c.Love);
            else if (k == "love_ts") long.TryParse(v, out c.LoveTs);
            else if (k == "screen_aware") c.ScreenAware = v == "1";
            else if (k == "system_alerts") c.SystemAlerts = v == "1";
            else if (k == "ai_comments") c.AiComments = v == "1";
            else if (k == "ai_model" && v != "") c.AiModel = v;
            else if (k == "ai_backend" && v != "") c.AiBackend = v;
            else if (k == "phone_on") c.PhoneOn = v == "1";
            else if (k == "phone_only_away") c.PhoneOnlyAway = v == "1";
            else if (k == "ntfy_topic") c.NtfyTopic = v;
            else if (k == "last_todo_noon") c.LastTodoNoon = v;
            else if (k == "last_todo_eve") c.LastTodoEve = v;
            else if (k == "last_todo_party") c.LastTodoParty = v;
            else if (k == "birthday") c.Birthday = v;
            else if (k == "birthday_asked") c.BirthdayAsked = v == "1";
            else if (k == "hat_from") c.HatFrom = v;
            else if (k == "last_special") c.LastSpecial = v;
            else if (k == "love_level") int.TryParse(v, out c.LoveLevel);
            else if (k.StartsWith("color_") && c.Colors.ContainsKey(k.Substring(6))) c.Colors[k.Substring(6)] = v;
        }
        if (c.Scale < 1) c.Scale = 1;
        return c;
    }

    public void Save()
    {
        var lines = new List<string> {
            "look=" + Look,
            "emote=" + Emote,
            "muted=" + (Muted ? "1" : "0"),
            "voice=" + (Voice ? "1" : "0"),
            "voice_vol=" + VoiceVol,
            "snooze_until=" + SnoozeUntil.Ticks,
            "scale=" + Scale,
            "seconds=" + Seconds.ToString(CultureInfo.InvariantCulture),
            "hide_games=" + (HideInGames ? "1" : "0"),
            "hide_fullscreen=" + (HideInFullscreen ? "1" : "0"),
            "pet=" + (Pet ? "1" : "0"),
            "pet_topmost=" + (PetTopmost ? "1" : "0"),
            "pet_small=" + (PetSmall ? "1" : "0"),
            "anim=" + (AnimOn ? "1" : "0"),
            "mini_always=" + (MiniAlways ? "1" : "0"),
            "mini_video=" + (MiniVideo ? "1" : "0"),
            "mini_game=" + (MiniGame ? "1" : "0"),
            "mini_dx=" + MiniDx,
            "mini_dy=" + MiniDy,
            "pet_x=" + PetX,
            "pet_y=" + PetY,
            "last_greet=" + LastGreet,
            "last_stretch=" + LastStretch,
            "spotify=" + (Spotify ? "1" : "0"),
            "break_minutes=" + BreakMinutes,
            "city=" + City,
            "city_lat=" + CityLat,
            "city_lon=" + CityLon,
            "last_weather=" + LastWeather,
            "last_summary=" + LastSummary,
            "love=" + Love,
            "love_ts=" + LoveTs,
            "screen_aware=" + (ScreenAware ? "1" : "0"),
            "system_alerts=" + (SystemAlerts ? "1" : "0"),
            "ai_comments=" + (AiComments ? "1" : "0"),
            "ai_model=" + AiModel,
            "ai_backend=" + AiBackend,
            "phone_on=" + (PhoneOn ? "1" : "0"),
            "phone_only_away=" + (PhoneOnlyAway ? "1" : "0"),
            "ntfy_topic=" + NtfyTopic,
            "last_todo_noon=" + LastTodoNoon,
            "last_todo_eve=" + LastTodoEve,
            "last_todo_party=" + LastTodoParty,
            "birthday=" + Birthday,
            "birthday_asked=" + (BirthdayAsked ? "1" : "0"),
            "hat_from=" + HatFrom,
            "last_special=" + LastSpecial,
            "love_level=" + LoveLevel,
        };
        foreach (var k in GroupKeys) lines.Add("color_" + k + "=" + Colors[k]);
        try { File.WriteAllLines(FilePath, lines); } catch { }
    }

    // Canlı ayar nesnesini (pencereler aynı nesneyi paylaşıyor) diskteki hâliyle günceller.
    public void CopyFrom(Config o)
    {
        foreach (var f in typeof(Config).GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance))
            f.SetValue(this, f.GetValue(o));
    }

    // Başka süreçlerin yazdığı ayarları ezmemek için: diskten taze oku, tek alanı değiştir, kaydet.
    public static void Patch(Action<Config> change)
    {
        var c = Load();
        change(c);
        c.Save();
    }

    public static string[] Looks()
    {
        var d = Path.Combine(Dir, "frames");
        return Directory.Exists(d) ? Directory.GetDirectories(d).Select(Path.GetFileName).Where(n => !n.EndsWith("-onceki") && n != "mini").OrderBy(n => n == "klasik" ? "" : n).ToArray() : new string[0];
    }
}

// Ekranda gösterilecek tek bir bildirim: balon metinleri, ifade, ses, tıklanınca açılacak uygulama.
class Event
{
    public string Mode = "done", Title = "", Body = "", Footer = "", Emote = "mutlu", Sound = "done.wav", Prefix = "wave_", Click = "claude", Session = "";
    public bool Phoned; // telefona zaten gönderildi (yalnızca süreç içinde)

    public string Encode()
    {
        var s = string.Join("\n", new[] { Mode, Title, Body, Footer, Emote, Sound, Prefix, Click, Session }.Select(x => (x ?? "").Replace("\n", " ")));
        return Convert.ToBase64String(Encoding.UTF8.GetBytes(s)).Replace('+', '-').Replace('/', '_');
    }

    public static Event Decode(string b64)
    {
        var p = Encoding.UTF8.GetString(Convert.FromBase64String(b64.Replace('-', '+').Replace('_', '/'))).Split('\n');
        return new Event { Mode = p[0], Title = p[1], Body = p[2], Footer = p[3], Emote = p[4], Sound = p[5], Prefix = p[6], Click = p[7], Session = p.Length > 8 ? p[8] : "" };
    }
}

// Hook verisinden ve saatten bildirimin içeriğini ve duygusunu çıkarır.
static class EventBuilder
{
    static readonly Random rnd = new Random();

    static readonly Dictionary<string, string[]> Apps = new Dictionary<string, string[]> {
        { "whatsapp", new[] { "WhatsApp", "Yeni bir mesajınız var!" } },
        { "telegram", new[] { "Telegram", "Telegram'dan mesaj var!" } },
        { "discord", new[] { "Discord", "Discord'da yeni mesaj!" } },
        { "outlook", new[] { "Outlook", "Toplantın yaklaşıyor!" } },
    };

    public static Event Build(string mode, string[] args, string stdin, Config cfg)
    {
        var hook = new Dictionary<string, object>();
        if (!string.IsNullOrWhiteSpace(stdin))
            try { hook = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(stdin); } catch { }
        string project = "";
        object cwd;
        if (hook.TryGetValue("cwd", out cwd) && cwd != null) project = Path.GetFileName(cwd.ToString().TrimEnd('\\', '/'));
        if (cwd != null && cwd.ToString().TrimEnd('\\', '/').EndsWith(Path.Combine("sakura", "brain"), StringComparison.OrdinalIgnoreCase)) return null;
        bool random = !Emotes.Keys.Contains(cfg.Emote);
        var now = DateTime.Now;
        var ev = new Event { Mode = mode, Title = project, Emote = Emotes.Pick(mode, cfg) };
        object sid;
        if (hook.TryGetValue("session_id", out sid) && sid != null) ev.Session = sid.ToString();
        if (mode == "work") return ev; // Claude bir işe başladı: yalnızca masaüstü arkadaşı düşünür.

        if (mode == "msg")
        {
            string app = args.Length > 1 && Apps.ContainsKey(args[1]) ? args[1] : "whatsapp";
            ev.Title = Apps[app][0];
            ev.Body = Apps[app][1];
            ev.Sound = "msg.wav";
            ev.Click = app;
            Stats.Log("msg", app, 0);
            return ev;
        }
        if (mode == "error")
        {
            ev.Body = "Bir sorun çıktı, işi bitiremedim…";
            ev.Footer = "Bakabilir misin?";
            ev.Emote = "uzgun";
            ev.Sound = "ask.wav";
            ev.Prefix = "idle_";
            Stats.Log("error", project, 0);
            return ev;
        }
        if (mode == "ask")
        {
            object m;
            string msg = hook.TryGetValue("message", out m) && m != null ? m.ToString() : "";
            var tool = Regex.Match(msg, @"use ([\w\-\.]+)");
            if (msg.IndexOf("permission", StringComparison.OrdinalIgnoreCase) >= 0)
                ev.Body = tool.Success ? "İzin vermen gerekiyor: " + FriendlyTool(tool.Groups[1].Value) : "İzin vermen gerekiyor";
            else if (msg.IndexOf("waiting", StringComparison.OrdinalIgnoreCase) >= 0)
                ev.Body = "Seni bekliyorum…";
            else ev.Body = "Bakar mısın?";
            ev.Sound = "ask.wav";
            ev.Prefix = "idle_";
            return ev;
        }

        // done: balonda işin özeti, duruma göre ruh hali.
        object tp;
        DateTime started = DateTime.MinValue;
        string summary = null;
        if (hook.TryGetValue("transcript_path", out tp) && tp != null) summary = Transcript.Summary(tp.ToString(), out started);
        ev.Body = string.IsNullOrEmpty(summary) ? "İşim bitti!" : summary;
        var took = started == DateTime.MinValue ? TimeSpan.Zero : now - started;
        Stats.Log("done", project, took.TotalMinutes);
        if (now.Hour < 5)
        {
            ev.Footer = "Bitti… hadi uyu artık";
            if (random) ev.Emote = "uykulu";
        }
        else if (took.TotalMinutes >= 5)
        {
            ev.Footer = string.Format("Sonunda bitti! ({0} dk)", (int)took.TotalMinutes);
            if (random) ev.Emote = rnd.Next(2) == 0 ? "gurur" : "nese";
        }
        else if (now.Hour < 12 && cfg.LastGreet != now.ToString("yyyy-MM-dd"))
        {
            ev.Footer = "Günaydın!";
            cfg.LastGreet = now.ToString("yyyy-MM-dd");
            cfg.Save();
        }
        return ev;
    }

    static string FriendlyTool(string t)
    {
        if (t == "Bash" || t == "PowerShell") return "komut çalıştırma";
        if (t == "Edit" || t == "Write") return "dosya düzenleme";
        if (t.StartsWith("mcp__")) return t.Split(new[] { "__" }, StringSplitOptions.None).Last();
        return t;
    }
}

// Claude Code oturum kaydından (jsonl) son turun özetini ve başlangıç saatini çıkarır.
static class Transcript
{
    public static string Summary(string path, out DateTime started)
    {
        started = DateTime.MinValue;
        try
        {
            if (!File.Exists(path)) return null;
            string[] lines;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                long take = Math.Min(fs.Length, 4L * 1024 * 1024);
                fs.Seek(-take, SeekOrigin.End);
                var buf = new byte[take];
                int read = 0;
                while (read < take) { int n = fs.Read(buf, read, (int)take - read); if (n <= 0) break; read += n; }
                lines = Encoding.UTF8.GetString(buf, 0, read).Split('\n');
            }
            var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            string recap = null, text = null;
            for (int i = lines.Length - 1; i >= 0; i--)
            {
                var l = lines[i];
                bool isUser = l.Contains("\"type\":\"user\""), isAsst = l.Contains("\"type\":\"assistant\"");
                if (!isUser && !isAsst) continue;
                Dictionary<string, object> d;
                try { d = js.Deserialize<Dictionary<string, object>>(l); } catch { continue; }
                var msg = d.ContainsKey("message") ? d["message"] as Dictionary<string, object> : null;
                if (msg == null) continue;
                object content = msg.ContainsKey("content") ? msg["content"] : null;
                if (isUser)
                {
                    if (d.ContainsKey("isMeta") && true.Equals(d["isMeta"])) continue;
                    var arr = content as System.Collections.ArrayList;
                    bool toolResult = arr != null && arr.Cast<object>().Any(x => x is Dictionary<string, object> && "tool_result".Equals(((Dictionary<string, object>)x).ContainsKey("type") ? ((Dictionary<string, object>)x)["type"] : null));
                    if (toolResult) continue;
                    // Kullanıcının son gerçek mesajı: turun başlangıcı.
                    object ts;
                    DateTime t;
                    if (d.TryGetValue("timestamp", out ts) && DateTime.TryParse(ts.ToString(), CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out t))
                        started = t.ToLocalTime();
                    break;
                }
                var parts = content as System.Collections.ArrayList;
                if (parts == null) continue;
                foreach (var o in parts.Cast<object>().Reverse())
                {
                    var p = o as Dictionary<string, object>;
                    if (p == null || !p.ContainsKey("type")) continue;
                    if (recap == null && "tool_use".Equals(p["type"]) && p.ContainsKey("name") && p["name"].ToString().EndsWith("wrap_up"))
                    {
                        var inp = p["input"] as Dictionary<string, object>;
                        if (inp != null && inp.ContainsKey("recap")) recap = inp["recap"].ToString();
                    }
                    if (text == null && "text".Equals(p["type"]) && p.ContainsKey("text")) text = p["text"].ToString();
                }
            }
            return FirstSentence(recap ?? text);
        }
        catch { return null; }
    }

    static string FirstSentence(string s)
    {
        if (string.IsNullOrWhiteSpace(s)) return null;
        s = Regex.Replace(s, @"[`*_#>\[\]]", "");
        s = Regex.Replace(s, @"\([^)]*\)", "");
        s = Regex.Replace(s, @"\s+", " ").Trim();
        var m = Regex.Match(s, @"^(.+?[.!?…])(\s|$)");
        if (m.Success) s = m.Groups[1].Value;
        s = s.TrimEnd('.', ':', ';');
        return s.Length > 90 ? s.Substring(0, 88).TrimEnd() + "…" : s;
    }
}

// Tam ekran oyun / sunum ya da (isteğe bağlı) tam ekran video varken rahatsız etme.
static class Quiet
{
    [DllImport("shell32.dll")] static extern int SHQueryUserNotificationState(out int state);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern IntPtr GetShellWindow();
    [DllImport("user32.dll")] static extern IntPtr GetDesktopWindow();
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }

    // Öndeki pencere bulunduğu monitörün tamamını kaplıyor mu (masaüstü ve görev çubuğu hariç)?
    public static bool ForegroundFullscreen()
    {
        var h = GetForegroundWindow();
        if (h == IntPtr.Zero || h == GetShellWindow() || h == GetDesktopWindow()) return false;
        RECT r;
        if (!GetWindowRect(h, out r)) return false;
        var b = Screen.FromHandle(h).Bounds;
        return r.Left <= b.Left && r.Top <= b.Top && r.Right >= b.Right && r.Bottom >= b.Bottom;
    }

    public static bool ShouldHide(Config cfg)
    {
        int st;
        if (SHQueryUserNotificationState(out st) != 0) return false;
        if (st == 4) return cfg.HideInGames && !cfg.MiniGame;                 // sunum modu
        if (st == 3) return cfg.HideInGames && !cfg.MiniGame && ForegroundFullscreen(); // D3D tam ekran (oyun); "Oyunda mini" açıksa gizlenmez, mini olur
        if (st == 2) return cfg.HideInFullscreen && ForegroundFullscreen();   // tam ekran uygulama (ör. YouTube)
        return false;
    }

    public static int State() { int st; return SHQueryUserNotificationState(out st) == 0 ? st : 0; }

    static readonly string[] Games = { "robloxplayerbeta", "valorant-win64-shipping", "leagueoflegends", "cs2", "gta5", "fortniteclient-win64-shipping", "r5apex", "eldenring", "minecraft.windows" };
    static readonly string[] NotGames = { "explorer", "applicationframehost", "sakura", "claude", "code", "devenv", "powerpnt", "winword", "excel" };

    // Oyun oynanıyor mu: D3D tam ekran, bilinen oyun süreci ya da tarayıcı/video oynatıcı olmayan tam ekran pencere.
    public static bool GameNow(out string why)
    {
        string proc, title;
        Screen2.Foreground(out proc, out title);
        string p = proc.ToLowerInvariant();
        why = proc;
        if (Games.Contains(p)) return true;
        if (NotGames.Contains(p) || Screen2.IsBrowser(p) || Screen2.IsVideoApp(p)) return false;
        int st = State();
        return (st == 3 || st == 2) && ForegroundFullscreen();
    }
}

// Sakura'ya tıklanınca ilgili uygulamayı öne getirir.
static class AppFocus
{
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);

    static readonly Dictionary<string, string[]> Procs = new Dictionary<string, string[]> {
        { "claude", new[] { "Claude" } },
        { "whatsapp", new[] { "WhatsApp", "WhatsApp.Root" } },
        { "telegram", new[] { "Telegram" } },
        { "discord", new[] { "Discord" } },
        { "outlook", new[] { "olk", "OUTLOOK" } },
        { "spotify", new[] { "Spotify" } },
    };

    public static void Open(string target)
    {
        string[] names;
        if (target != null && target.StartsWith("file:"))
        {
            try { Process.Start("explorer.exe", "/select,\"" + target.Substring(5) + "\""); } catch { }
            return;
        }
        if (target == null || !Procs.TryGetValue(target, out names)) return;
        foreach (var n in names)
            foreach (var p in Process.GetProcessesByName(n))
            {
                var h = p.MainWindowHandle;
                if (h == IntPtr.Zero) continue;
                if (IsIconic(h)) ShowWindow(h, 9);
                SetForegroundWindow(h);
                return;
            }
        if (target == "whatsapp") try { Process.Start("whatsapp:"); } catch { }
    }
}

// Pixel art konuşma balonu: başlık (proje/uygulama), metin (en çok 3 satır) ve alt not.
// Sevgi barı (fare üstündeyken / sevgi değişince): parlak kalp + pembe dolum çubuğu + yüzde. Pürüzsüz çizilir.
static class LoveBar
{
    static GraphicsPath Round(RectangleF r, float rad)
    {
        var p = new GraphicsPath();
        float d = Math.Min(rad * 2, Math.Min(r.Width, r.Height));
        p.AddArc(r.X, r.Y, d, d, 180, 90);
        p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }

    // Kalp eğrisi: x = 16 sin³t, y = 13 cos t − 5 cos 2t − 2 cos 3t − cos 4t
    static GraphicsPath Heart(float cx, float cy, float size)
    {
        var pts = new PointF[90];
        for (int i = 0; i < pts.Length; i++)
        {
            double t = 2 * Math.PI * i / pts.Length;
            double x = 16 * Math.Pow(Math.Sin(t), 3), y = 13 * Math.Cos(t) - 5 * Math.Cos(2 * t) - 2 * Math.Cos(3 * t) - Math.Cos(4 * t);
            pts[i] = new PointF(cx + (float)(x * size / 34), cy - (float)(y * size / 34));
        }
        var p = new GraphicsPath();
        p.AddPolygon(pts);
        return p;
    }

    public static void Draw(Graphics g, float x, float y, float z, int love, string title)
    {
        var st = g.Save();
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        float hs = 30 * z, hcx = x + 15 * z, hcy = y + 15 * z;
        var track = new RectangleF(x + 20 * z, y + 8 * z, 128 * z, 14 * z);
        float fw = Math.Max(14 * z, track.Width * Math.Max(0, Math.Min(100, love)) / 100f);
        var fill = new RectangleF(track.X, track.Y, fw, track.Height);
        var shade = Color.FromArgb(80, 40, 20, 50);
        // gölge
        using (var sh = new SolidBrush(shade))
        using (var p = Round(RectangleF.Inflate(track, 2 * z, 2 * z), 9 * z))
        using (var h = Heart(hcx, hcy, hs))
        {
            var m = new Matrix();
            m.Translate(0, 2 * z);
            p.Transform(m); h.Transform(m);
            g.FillPath(sh, p); g.FillPath(sh, h);
        }
        // çubuk: beyaz kenar, koyu yatak, pembe dolum, parlama
        using (var white = new SolidBrush(Color.White))
        using (var p = Round(RectangleF.Inflate(track, 2 * z, 2 * z), 9 * z)) g.FillPath(white, p);
        using (var bed = new SolidBrush(Color.FromArgb(70, 55, 85)))
        using (var p = Round(track, 7 * z)) g.FillPath(bed, p);
        using (var gb = new LinearGradientBrush(new RectangleF(track.X - 1, track.Y, track.Width + 2, track.Height), Color.FromArgb(255, 140, 190), Color.FromArgb(235, 60, 150), LinearGradientMode.Horizontal))
        using (var p = Round(fill, 7 * z)) g.FillPath(gb, p);
        if (fw > 24 * z)
            using (var hl = new SolidBrush(Color.FromArgb(110, 255, 255, 255)))
            using (var p = Round(new RectangleF(track.X + 14 * z, track.Y + 2 * z, fw - 18 * z, 3 * z), 1.5f * z)) g.FillPath(hl, p);
        // yüzde: beyaz yazı, koyu kontur
        using (var path = new GraphicsPath())
        using (var ff = new FontFamily("Segoe UI"))
        using (var fmt = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
        {
            path.AddString("%" + love, ff, (int)FontStyle.Bold, 11 * z, new RectangleF(track.X + 10 * z, track.Y - 1 * z, track.Width - 10 * z, track.Height + 2 * z), fmt);
            using (var pen = new Pen(Color.FromArgb(90, 40, 80), 2.6f * z) { LineJoin = LineJoin.Round }) g.DrawPath(pen, path);
            using (var w = new SolidBrush(Color.White)) g.FillPath(w, path);
        }
        // unvan: çubuğun altında küçük beyaz etiket
        if (!string.IsNullOrEmpty(title))
            using (var tf = new Font("Segoe UI", 9 * z, FontStyle.Bold, GraphicsUnit.Pixel))
            {
                var ts = g.MeasureString(title, tf);
                var tr = new RectangleF(track.Right - ts.Width - 6 * z, track.Bottom + 4 * z, ts.Width + 8 * z, ts.Height + 1 * z);
                using (var bg = new SolidBrush(Color.FromArgb(225, 255, 255, 255)))
                using (var p = Round(tr, tr.Height / 2)) g.FillPath(bg, p);
                using (var tb = new SolidBrush(Color.FromArgb(200, 50, 120))) g.DrawString(title, tf, tb, tr.X + 4 * z, tr.Y + 0.5f * z);
            }
        // kalp: beyaz kenar, pembe degrade, parlama
        using (var white = new SolidBrush(Color.White))
        using (var h = Heart(hcx, hcy, hs)) g.FillPath(white, h);
        float inner = hs - 4 * z;
        using (var hb = new LinearGradientBrush(new RectangleF(hcx - inner / 2, hcy - inner / 2 - 1, inner, inner + 2), Color.FromArgb(255, 120, 170), Color.FromArgb(220, 45, 120), LinearGradientMode.Vertical))
        using (var h = Heart(hcx, hcy, inner)) g.FillPath(hb, h);
        using (var gl = new SolidBrush(Color.FromArgb(170, 255, 255, 255)))
            g.FillEllipse(gl, hcx - inner * 0.32f, hcy - inner * 0.33f, inner * 0.24f, inner * 0.17f);
        g.Restore(st);
    }
}

// Luna'nın sesi: kelime söylemez; yazıdaki ünlüler pentatonik notalara denk gelen kısa, nefesli flüt sesleri olur
// (Undertale/Animal Crossing tarzı). Hepsi anlık sentez, ses dosyası yok. Duygu tonu, hızı ve kaymayı değiştirir.
static class Voice
{
    const int SR = 22050;
    const string Vowels = "aeıioöuü";
    static readonly int[] Scale = { 0, 2, 4, 7, 9, 12, 14, 16 };
    static System.Media.SoundPlayer player;

    // (temel frekans, hece ms, harf/sn, nota içi kayma, yarım ton yukarı)
    static void Params(string emote, out double f0, out int ms, out double cps, out double slide, out double up)
    {
        f0 = 1200; ms = 46; cps = 26; slide = 0; up = 0;
        switch (emote ?? "")
        {
            case "mutlu": case "nese": case "gurur": case "goz_kirp": case "sevgi":
                f0 = 1300; ms = 42; cps = 30; slide = 0.1; up = 2; break;
            case "uzgun": case "agla": f0 = 900; ms = 62; cps = 17; slide = -0.08; break;
            case "uykulu": f0 = 850; ms = 70; cps = 14; slide = -0.05; break;
            case "saskin": f0 = 1250; ms = 46; cps = 28; slide = 0.18; up = 3; break;
            case "sinirli": f0 = 1000; ms = 40; cps = 32; slide = -0.04; break;
            case "utangac": f0 = 1150; ms = 40; cps = 22; slide = 0.05; break;
            case "dusunce": f0 = 1050; ms = 55; cps = 18; break;
        }
    }

    // Metni heceler: duyulan her harf için note(konum, harf sırası) çağrılır. Dönüş: son konum; voiced: son hecenin bittiği yer.
    static int Walk(string s, int step, int n, int size, double maxSec, Action<int, int> note, out int voiced)
    {
        int pos = 0;
        voiced = 0;
        for (int i = 0; i < s.Length && pos + n < size; i++)
        {
            char ch = s[i];
            if (".?!~…".IndexOf(ch) >= 0) { pos += (int)(SR * 0.28); continue; }
            if (ch == ',') { pos += (int)(SR * 0.16); continue; }
            if (!char.IsLetter(ch)) { pos += step; continue; }
            if (i % 2 == 1 && Vowels.IndexOf(ch) < 0) { pos += step; continue; } // ünsüzlerin yarısı sessiz: akıcı mırıltı
            if (note != null) note(pos, i);
            voiced = pos + n;
            pos += step;
            if (pos > SR * maxSec) break; // uzun metinde yalnız baştaki kısmı konuşur
        }
        return pos;
    }

    static int BufSize(string s, double cps, int n, double maxSec) { return (int)(SR * Math.Min(maxSec + 0.5, s.Length / cps + 1)) + n; }

    // Ses gerçekte kaç saniye sürer (ağız bu kadar oynar): son nokta ve ~ sessizliği sayılmaz.
    public static double Seconds(string text, string emote, double maxSec)
    {
        double f0, cps, slide, up; int ms, voiced;
        Params(emote, out f0, out ms, out cps, out slide, out up);
        string s = (text ?? "").ToLowerInvariant();
        int n = SR * ms / 1000;
        Walk(s, (int)(SR / cps), n, BufSize(s, cps, n, maxSec), maxSec, null, out voiced);
        return (double)voiced / SR;
    }

    public static byte[] Synth(string text, string emote, int vol, double maxSec)
    {
        double f0, cps, slide, up; int ms, voiced;
        Params(emote, out f0, out ms, out cps, out slide, out up);
        string s = (text ?? "").ToLowerInvariant();
        int step = (int)(SR / cps), n = SR * ms / 1000;
        var buf = new float[BufSize(s, cps, n, maxSec)];
        var rnd = new Random(7);
        int pos = Walk(s, step, n, buf.Length, maxSec, (at, i) =>
        {
            char ch = s[i];
            int vi = Vowels.IndexOf(ch);
            int k = Scale[(vi >= 0 ? vi : ch) % Scale.Length];
            int qi = s.IndexOf('?', i);
            bool q = qi >= 0 && qi - i < 4; // soruya yaklaşınca yükselir
            double f = f0 * Math.Pow(2, (k / 2.0 + (q ? 3 : 0) + up) / 12);
            double ph = 0;
            for (int j = 0; j < n; j++)
            {
                double tt = (double)j / SR;
                ph += 2 * Math.PI * f * (1 + slide * j / n) / SR;
                double v = Math.Sin(ph) + 0.3 * Math.Sin(2 * ph) * Math.Exp(-tt * 30) + 0.05 * (rnd.NextDouble() * 2 - 1) * Math.Exp(-tt * 80);
                double env = Math.Min(1, tt / 0.004) * Math.Exp(-tt / (ms / 1000.0 / 3));
                buf[at + j] += (float)(v * env);
            }
        }, out voiced);
        int len = Math.Min(buf.Length, pos + SR / 4);
        float g = 0.32f * Math.Max(0, Math.Min(100, vol)) / 100f;
        var mem = new MemoryStream();
        var w = new BinaryWriter(mem);
        w.Write(Encoding.ASCII.GetBytes("RIFF")); w.Write(36 + len * 2); w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
        w.Write(16); w.Write((short)1); w.Write((short)1); w.Write(SR); w.Write(SR * 2); w.Write((short)2); w.Write((short)16);
        w.Write(Encoding.ASCII.GetBytes("data")); w.Write(len * 2);
        for (int i = 0; i < len; i++) w.Write((short)(Math.Max(-1, Math.Min(1, buf[i] * g)) * 32767));
        return mem.ToArray();
    }

    public static void Say(Config cfg, string text, string emote, double maxSec)
    {
        if (cfg.Muted || !cfg.Voice || string.IsNullOrWhiteSpace(text)) return;
        try
        {
            var p = new System.Media.SoundPlayer(new MemoryStream(Synth(text, emote, cfg.VoiceVol, maxSec)));
            if (player != null) player.Stop();
            player = p;
            p.Play();
        }
        catch { }
    }
}

// Konuşma sahnesindeki sahte sohbet penceresi: kurgusaldır, hiçbir uygulamaya bağlanmaz, logo içermez.
class FakeChat : Form
{
    class Msg { public bool Mine; public string Text; }
    static readonly Font HeadFont = new Font("Segoe UI", 16f, FontStyle.Bold, GraphicsUnit.Pixel);
    static readonly Font TimeFont = new Font("Segoe UI", 14f, FontStyle.Regular, GraphicsUnit.Pixel);
    static readonly Font MsgFont = new Font("Segoe UI", 17f, FontStyle.Regular, GraphicsUnit.Pixel);
    const int Head = 44, Box = 52, Edge = 14;
    readonly List<Msg> msgs = new List<Msg>();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer { Interval = 75 };
    string typing = "", target, reply;
    int wait;

    public FakeChat(Rectangle r)
    {
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = r;
        ShowInTaskbar = false;
        TopMost = true;
        DoubleBuffered = true;
        BackColor = Color.FromArgb(32, 30, 38);
        timer.Tick += (s, e) => Step();
    }

    protected override bool ShowWithoutActivation { get { return true; } }

    public void Add(bool mine, string text) { msgs.Add(new Msg { Mine = mine, Text = text }); Invalidate(); }
    public void Type(string text) { target = text; typing = ""; timer.Start(); }
    public void Reply(string text) { reply = text; wait = 16; timer.Start(); Invalidate(); }

    void Step()
    {
        if (target != null)
        {
            if (typing.Length < target.Length) typing = target.Substring(0, typing.Length + 1);
            else { Add(true, target); target = null; typing = ""; if (reply == null) timer.Stop(); }
        }
        else if (reply != null && --wait <= 0) { Add(false, reply); reply = null; timer.Stop(); }
        Invalidate();
    }

    static System.Drawing.Drawing2D.GraphicsPath Round(RectangleF r, float d)
    {
        var p = new System.Drawing.Drawing2D.GraphicsPath();
        p.AddArc(r.X, r.Y, d, d, 180, 90);
        p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        using (var soft = new SolidBrush(Color.FromArgb(160, 155, 175)))
        using (var head = new SolidBrush(Color.FromArgb(44, 41, 52)))
        using (var mine = new SolidBrush(Color.FromArgb(92, 72, 150)))
        using (var other = new SolidBrush(Color.FromArgb(52, 49, 60)))
        {
            g.FillRectangle(head, 0, 0, Width, Head);
            g.DrawString("Sohbet", HeadFont, Brushes.White, Edge, 11);
            g.DrawString("03:12", TimeFont, soft, Width - 58, 13);
            float y = Head + Edge, maxW = Width * 0.72f;
            foreach (var m in msgs.Concat(reply != null && target == null ? new[] { new Msg { Text = "…" } } : new Msg[0]))
            {
                var sz = g.MeasureString(m.Text, MsgFont, (int)maxW);
                float w = sz.Width + 22, h = sz.Height + 14, x = m.Mine ? Width - Edge - w : Edge;
                using (var b = Round(new RectangleF(x, y, w, h), 18)) g.FillPath(m.Mine ? mine : other, b);
                g.DrawString(m.Text, MsgFont, Brushes.White, new RectangleF(x + 11, y + 7, sz.Width + 2, sz.Height + 2));
                y += h + 10;
            }
            var box = new RectangleF(Edge, Height - Box - 8, Width - Edge * 2, Box - 8);
            using (var b = Round(box, 20)) g.FillPath(other, b);
            bool empty = typing.Length == 0;
            g.DrawString(empty ? "Bir şeyler yaz…" : typing + "|", MsgFont, empty ? soft : Brushes.White, box.X + 16, box.Y + 9);
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) timer.Dispose();
        base.Dispose(disposing);
    }
}

// 5 Kas 2026 (Dino istedi): balonda renkli emoji. GDI+ renkli emoji çizemiyor (siyah kutu çıkıyordu). Emoji yerine
// Twemoji resmi çizilir (jdecked/twemoji 15.1.0, CC-BY 4.0, emoji\LISANS.txt). Resim yoksa ilk görüldüğünde
// jsDelivr'den indirilip emoji\ klasörüne kaydedilir; inene kadar yeri boş kalır (Sakura zaten sürekli yeniden çiziliyor).
// Twemoji'de olmayan sembol (ör. ♪) yazı olarak çizilir. Emoji içermeyen metin eskisi gibi tek DrawString'le çizilir.
static class EmojiText
{
    static readonly string Dir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "emoji");
    const string Url = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/";
    static readonly Dictionary<string, Image> cache = new Dictionary<string, Image>();
    static readonly HashSet<string> yok = new HashSet<string>(), iniyor = new HashSet<string>();
    static readonly object kilit = new object();
    static readonly StringFormat Typo = MakeTypo();

    static StringFormat MakeTypo()
    {
        var f = (StringFormat)StringFormat.GenericTypographic.Clone();
        f.FormatFlags |= StringFormatFlags.MeasureTrailingSpaces;
        return f;
    }

    class Tok { public string Text; public string Key; public float W; public bool Br; }
    class Yer { public Tok T; public float X; public int Line; }

    static bool EmojiCp(int cp)
    {
        return (cp >= 0x1F000 && cp <= 0x1FAFF) || (cp >= 0x2600 && cp <= 0x27BF) || (cp >= 0x2B00 && cp <= 0x2BFF) ||
               (cp >= 0x2300 && cp <= 0x23FF) || cp == 0x203C || cp == 0x2049 || cp == 0x3030 || cp == 0x303D ||
               cp == 0x3297 || cp == 0x3299 || cp == 0x2122 || cp == 0x2139;
    }

    public static bool Has(string s)
    {
        if (string.IsNullOrEmpty(s)) return false;
        for (int i = 0; i < s.Length; i++)
        {
            int cp = char.IsHighSurrogate(s[i]) && i + 1 < s.Length ? char.ConvertToUtf32(s[i], s[i + 1]) : s[i];
            if (EmojiCp(cp)) return true;
        }
        return false;
    }

    // Metni sözcük / boşluk / emoji parçalarına ayırır. Emoji kümesi: FE0F, ten rengi, ZWJ dizisi, bayrak çifti, keycap.
    static List<Tok> Parcala(string s)
    {
        var r = new List<Tok>();
        var sb = new StringBuilder();
        Action bosalt = () => { if (sb.Length > 0) { r.Add(new Tok { Text = sb.ToString() }); sb.Clear(); } };
        int i = 0;
        while (i < s.Length)
        {
            char c = s[i];
            if (c == '\n') { bosalt(); r.Add(new Tok { Br = true, Text = "" }); i++; continue; }
            if (c == '\r') { i++; continue; }
            int cp = char.IsHighSurrogate(c) && i + 1 < s.Length ? char.ConvertToUtf32(c, s[i + 1]) : c;
            bool keycap = (char.IsDigit(c) || c == '#' || c == '*') && i + 1 < s.Length && (s[i + 1] == '️' || s[i + 1] == '⃣') &&
                          (s[i + 1] == '⃣' || (i + 2 < s.Length && s[i + 2] == '⃣'));
            if (!EmojiCp(cp) && !keycap)
            {
                if (c == ' ') { bosalt(); r.Add(new Tok { Text = " " }); }
                else sb.Append(c);
                i++;
                continue;
            }
            bosalt();
            int bas = i;
            var cps = new List<int> { cp };
            i += cp > 0xFFFF ? 2 : 1;
            bool zwj = false, bayrak = cp >= 0x1F1E6 && cp <= 0x1F1FF;
            while (i < s.Length)
            {
                int n = char.IsHighSurrogate(s[i]) && i + 1 < s.Length ? char.ConvertToUtf32(s[i], s[i + 1]) : s[i];
                int len = n > 0xFFFF ? 2 : 1;
                if (n == 0xFE0F || n == 0x20E3 || (n >= 0x1F3FB && n <= 0x1F3FF) || (n >= 0xE0020 && n <= 0xE007F)) { cps.Add(n); i += len; continue; }
                if (bayrak && cps.Count == 1 && n >= 0x1F1E6 && n <= 0x1F1FF) { cps.Add(n); i += len; continue; }
                if (n == 0x200D && i + 1 < s.Length)
                {
                    zwj = true; cps.Add(n); i += 1;
                    int m = char.IsHighSurrogate(s[i]) && i + 1 < s.Length ? char.ConvertToUtf32(s[i], s[i + 1]) : s[i];
                    cps.Add(m); i += m > 0xFFFF ? 2 : 1;
                    continue;
                }
                break;
            }
            // Twemoji dosya adı: ZWJ yoksa FE0F atılır
            string key = string.Join("-", cps.Where(x => zwj || x != 0xFE0F).Select(x => x.ToString("x")).ToArray());
            r.Add(new Tok { Text = s.Substring(bas, i - bas), Key = key });
        }
        bosalt();
        return r;
    }

    // Resim: önbellek → dosya → (yoksa) arka planda indir. null: henüz yok.
    static Image Resim(string key)
    {
        lock (kilit)
        {
            Image im;
            if (cache.TryGetValue(key, out im)) return im;
            if (yok.Contains(key)) return null;
            string yol = Path.Combine(Dir, key + ".png");
            if (File.Exists(yol))
            {
                try { using (var f = Image.FromFile(yol)) im = new Bitmap(f); cache[key] = im; return im; }
                catch { yok.Add(key); return null; }
            }
            if (File.Exists(Path.Combine(Dir, key + ".yok"))) { yok.Add(key); return null; }
            if (iniyor.Add(key)) ThreadPool.QueueUserWorkItem(_ => Indir(key));
            return null;
        }
    }

    static void Indir(string key)
    {
        try
        {
            Directory.CreateDirectory(Dir);
            System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
            using (var w = new System.Net.WebClient()) w.DownloadFile(Url + key + ".png", Path.Combine(Dir, key + ".png.tmp"));
            File.Move(Path.Combine(Dir, key + ".png.tmp"), Path.Combine(Dir, key + ".png"));
        }
        catch (System.Net.WebException ex)
        {
            var hr = ex.Response as System.Net.HttpWebResponse;
            if (hr != null && hr.StatusCode == System.Net.HttpStatusCode.NotFound)
                try { File.WriteAllText(Path.Combine(Dir, key + ".yok"), ""); } catch { }   // Twemoji'de yok: yazı olarak çizilir
        }
        catch { }
        lock (kilit) iniyor.Remove(key);
    }

    static bool Yazi(Tok t) { return t.Key == null || (Resim(t.Key) == null && yok.Contains(t.Key)); }

    // Sözcükleri satırlara yerleştirir. Taşan son satırın sonuna "…" konur.
    static List<Yer> Diz(Graphics g, string s, Font f, float maxW, int maxLines, out int satir, out float enGenis)
    {
        float boy = f.Height, ew = boy + 1;
        var toks = Parcala(s);
        foreach (var t in toks)
            if (!t.Br) t.W = Yazi(t) ? g.MeasureString(t.Text, f, PointF.Empty, Typo).Width : ew;
        var yer = new List<Yer>();
        float x = 0; int line = 0; enGenis = 0; bool tasti = false;
        foreach (var t in toks)
        {
            if (t.Br) { line++; x = 0; continue; }
            if (x > 0 && x + t.W > maxW && t.Text != " ") { line++; x = 0; }
            if (x == 0 && t.Text == " ") continue;   // satır başında boşluk yok
            if (maxLines > 0 && line >= maxLines) { tasti = true; break; }
            yer.Add(new Yer { T = t, X = x, Line = line });
            x += t.W;
            if (t.Text != " ") enGenis = Math.Max(enGenis, Math.Min(x, maxW));
        }
        if (tasti && yer.Count > 0)
        {
            var nokta = new Tok { Text = "…" };
            nokta.W = g.MeasureString("…", f, PointF.Empty, Typo).Width;
            var son = yer[yer.Count - 1];
            while (yer.Count > 1 && yer[yer.Count - 1].Line == son.Line && yer[yer.Count - 1].X + yer[yer.Count - 1].T.W + nokta.W > maxW)
                yer.RemoveAt(yer.Count - 1);
            var sn = yer[yer.Count - 1];
            yer.Add(new Yer { T = nokta, X = sn.X + sn.T.W, Line = sn.Line });
        }
        satir = yer.Count == 0 ? 0 : yer.Max(y => y.Line) + 1;
        return yer;
    }

    public static SizeF Measure(Graphics g, string s, Font f, int width)
    {
        int satir; float genis;
        Diz(g, s, f, width, 0, out satir, out genis);
        return new SizeF((float)Math.Ceiling(genis) + 1, satir * f.Height);
    }

    public static void Draw(Graphics g, string s, Font f, Brush b, RectangleF r)
    {
        int maxLines = Math.Max(1, (int)Math.Floor((r.Height + 2) / f.Height));
        int satir; float genis;
        var yer = Diz(g, s, f, r.Width, maxLines, out satir, out genis);
        float boy = f.Height;
        var eski = g.InterpolationMode;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        foreach (var y in yer)
        {
            float px = r.X + y.X, py = r.Y + y.Line * boy;
            if (y.T.Key != null)
            {
                var im = Resim(y.T.Key);
                if (im != null) { g.DrawImage(im, new RectangleF(px + 0.5f, py + 0.5f, boy - 1, boy - 1)); continue; }
                if (!yok.Contains(y.T.Key)) continue;   // iniyor: yer boş kalır
            }
            if (y.T.Text != " ") g.DrawString(y.T.Text, f, b, px, py, Typo);
        }
        g.InterpolationMode = eski;
    }
}

static class Bubble
{
    public static readonly Color Ink = Color.FromArgb(43, 29, 46);
    static readonly Color TitleColor = Color.FromArgb(214, 70, 120), FooterColor = Color.FromArgb(110, 90, 150);
    static readonly Font TitleFont = new Font("Segoe UI", 11f, FontStyle.Bold, GraphicsUnit.Pixel);
    static readonly Font BodyFont = new Font("Segoe UI", 12f, FontStyle.Bold, GraphicsUnit.Pixel);
    static readonly Font FooterFont = new Font("Segoe UI", 11f, FontStyle.Italic, GraphicsUnit.Pixel);
    const int MaxText = 210, Pad = 10, Tail = 6;

    static SizeF Measure(Graphics g, string s, Font f, int width)
    {
        if (EmojiText.Has(s)) return EmojiText.Measure(g, s, f, width);   // 5 Kas: renkli emoji
        return string.IsNullOrEmpty(s) ? SizeF.Empty : g.MeasureString(s, f, width);
    }

    public static Size Layout(Event ev) { return Layout(ev, MaxText, 3, false); }

    // down: kuyruk aşağıda (dikey videoda balon karakterin üstünde durur); lines: gövde metninin en çok satır sayısı.
    public static Size Layout(Event ev, int maxText, int lines, bool down)
    {
        using (var bmp = new Bitmap(1, 1))
        using (var g = Graphics.FromImage(bmp))
        {
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit;
            var t = Measure(g, ev.Title, TitleFont, maxText);
            var b = Measure(g, ev.Body, BodyFont, maxText);
            var f = Measure(g, ev.Footer, FooterFont, maxText);
            int w = (int)Math.Ceiling(Math.Max(t.Width, Math.Max(b.Width, f.Width))) + Pad * 2;
            int h = (int)Math.Ceiling(t.Height + Math.Min(b.Height, BodyFont.Height * lines + 2) + f.Height) + Pad * 2 - 4;
            return down ? new Size(Math.Max(110, w), Math.Max(40, h) + Tail) : new Size(Math.Max(110, w) + Tail, Math.Max(40, h));
        }
    }

    public static void Draw(Graphics g, Rectangle r, Event ev) { Draw(g, r, ev, 3, false); }

    // Çekim balonu: aynı balon Film kat büyük, Luna'nın başının üstünde, kuyruk aşağıda (telefonda okunsun).
    const float Film = 1.5f;
    const int FilmText = 240, FilmLines = 4;

    public static Size LayoutFilm(Event ev)
    {
        var s = Layout(ev, FilmText, FilmLines, true);
        return new Size((int)Math.Ceiling(s.Width * Film), (int)Math.Ceiling(s.Height * Film));
    }

    public static void DrawFilm(Graphics g, Rectangle r, Event ev)
    {
        // Luna'nın kendi yazısı kalsın: aynı balon, aynı keskin yazı, yalnız büyük çizilir.
        var st = g.Save();
        g.TranslateTransform(r.X, r.Y);
        g.ScaleTransform(Film, Film);
        Draw(g, new Rectangle(0, 0, (int)Math.Floor(r.Width / Film), (int)Math.Floor(r.Height / Film)), ev, FilmLines, true);
        g.Restore(st);
    }

    public static void Draw(Graphics g, Rectangle r, Event ev, int lines, bool down)
    {
        int bw = down ? r.Width : r.Width - Tail, bh = down ? r.Height - Tail : r.Height, bx = r.X, by = r.Y;
        using (var fill = new SolidBrush(Color.White))
        using (var ink = new SolidBrush(Ink))
        {
            g.FillRectangle(ink, bx + 2, by, bw - 4, bh);
            g.FillRectangle(ink, bx, by + 2, bw, bh - 4);
            g.FillRectangle(ink, bx + 1, by + 1, bw - 2, bh - 2);
            g.FillRectangle(fill, bx + 3, by + 2, bw - 6, bh - 4);
            g.FillRectangle(fill, bx + 2, by + 3, bw - 4, bh - 6);
            int ty = by + Math.Min(bh / 2, 20) - 5, tx = bx + bw / 2 - 5;
            for (int i = 0; i < 6; i++)
            {
                if (down)
                {
                    g.FillRectangle(ink, tx + i, by + bh - 2 + i, 11 - 2 * i, 1);
                    if (i < 5) g.FillRectangle(fill, tx + i + 1, by + bh - 3 + i, 9 - 2 * i, 1);
                    continue;
                }
                g.FillRectangle(ink, bx + bw - 2 + i, ty + i, 1, 11 - 2 * i);
                if (i < 5) g.FillRectangle(fill, bx + bw - 3 + i, ty + i + 1, 1, 9 - 2 * i);
            }
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit;
            float y = by + Pad - 2;
            int tw = bw - Pad * 2;
            if (!string.IsNullOrEmpty(ev.Title))
            {
                using (var tb = new SolidBrush(TitleColor))
                {
                    if (EmojiText.Has(ev.Title)) EmojiText.Draw(g, ev.Title, TitleFont, tb, new RectangleF(bx + Pad, y, tw, TitleFont.Height + 2));
                    else g.DrawString(ev.Title, TitleFont, tb, new RectangleF(bx + Pad, y, tw, TitleFont.Height + 2));
                }
                y += TitleFont.Height;
            }
            float bodyH = Math.Min(Measure(g, ev.Body, BodyFont, tw).Height, BodyFont.Height * lines + 2);
            if (EmojiText.Has(ev.Body)) EmojiText.Draw(g, ev.Body, BodyFont, ink, new RectangleF(bx + Pad, y, tw, bodyH));
            else g.DrawString(ev.Body, BodyFont, ink, new RectangleF(bx + Pad, y, tw, bodyH), new StringFormat { Trimming = StringTrimming.EllipsisWord });
            y += bodyH;
            if (!string.IsNullOrEmpty(ev.Footer))
                using (var fb = new SolidBrush(FooterColor)) g.DrawString(ev.Footer, FooterFont, fb, new RectangleF(bx + Pad, y, tw, FooterFont.Height + 2));
        }
    }
}

// Yüz ifadeleri (kareler emotes.py ile üretilir). "Rastgele"de duruma uygun olanlardan biri seçilir.
static class Emotes
{
    public static readonly string[] Keys = { "mutlu", "nese", "goz_kirp", "sevgi", "gurur", "utangac", "saskin", "uzgun", "agla", "uykulu", "sinirli", "dusunce" };
    public static readonly string[] Labels = { "Mutlu", "Neşeli", "Göz kırpma", "Sevgi", "Gururlu", "Utangaç", "Şaşkın", "Üzgün", "Ağlama", "Uykulu", "Kızgın", "Düşünceli" };
    static readonly Random rnd = new Random();

    public static string Pick(string mode, Config cfg)
    {
        if (Keys.Contains(cfg.Emote)) return cfg.Emote;
        string[] pool = mode == "ask" ? new[] { "saskin", "utangac" }
                      : mode == "msg" ? new[] { "sevgi", "saskin", "mutlu", "nese" }
                      : mode == "error" ? new[] { "uzgun" }
                      : new[] { "mutlu", "nese", "goz_kirp", "sevgi", "gurur" };
        return pool[rnd.Next(pool.Length)];
    }
}

// Hareket katmanı (sakura-animasyon skill'i): anims.json'daki klipler çizim anında kareyi kaydırır, döndürür, esnetir
// ve üstüne küçük efektler (kalp, parıltı, !, ?, ter damlası) çizer. Yeni çizim gerekmez; her ifade ve renkte çalışır.
// Bir durum klibi (bekleme, müzik, uyku, çalışıyor) hep döner; olaylar üstüne tek seferlik bir klip ekler.
// anims.json değişince Sakura yeniden derlenmeden okur (2 sn'de bir bakar).
static class Anim
{
    public class Key { public double T, V; public string Ease; }
    public class Clip
    {
        public string Name, Fx;
        public double Dur = 1, Px = 0.5, Py = 1, FxAt, FxDur = 1.5;
        public bool Loop;
        public Dictionary<string, List<Key>> Tracks = new Dictionary<string, List<Key>>();
    }
    public struct Pose
    {
        public double Dx, Dy, Rot, Sx, Sy, Px, Py;
        public static Pose Zero { get { return new Pose { Sx = 1, Sy = 1, Px = 0.5, Py = 1 }; } }
        public bool Still { get { return Math.Abs(Dx) < 0.05 && Math.Abs(Dy) < 0.05 && Math.Abs(Rot) < 0.02 && Math.Abs(Sx - 1) < 0.0005 && Math.Abs(Sy - 1) < 0.0005; } }
    }

    static readonly string FilePath = Path.Combine(Config.Dir, "anims.json");
    static Dictionary<string, Clip> clips = new Dictionary<string, Clip>();
    static Dictionary<string, string> triggers = new Dictionary<string, string>();
    static DateTime stamp = DateTime.MinValue, checkedAt = DateTime.MinValue;

    static void Reload()
    {
        var now = DateTime.Now;
        if ((now - checkedAt).TotalSeconds < 2) return;
        checkedAt = now;
        try
        {
            if (!File.Exists(FilePath)) { clips.Clear(); triggers.Clear(); return; }
            var t = File.GetLastWriteTime(FilePath);
            if (t == stamp) return;
            stamp = t;
            var root = new JavaScriptSerializer().DeserializeObject(File.ReadAllText(FilePath, Encoding.UTF8)) as Dictionary<string, object>;
            var cs = new Dictionary<string, Clip>();
            var ts = new Dictionary<string, string>();
            object o;
            if (root.TryGetValue("tetik", out o) && o is Dictionary<string, object>)
                foreach (var kv in (Dictionary<string, object>)o) if (kv.Value is string) ts[kv.Key] = (string)kv.Value;
            if (root.TryGetValue("klipler", out o) && o is Dictionary<string, object>)
                foreach (var kv in (Dictionary<string, object>)o)
                {
                    var d = kv.Value as Dictionary<string, object>;
                    if (d == null) continue;
                    var c = new Clip { Name = kv.Key };
                    if (d.TryGetValue("sure", out o)) c.Dur = Math.Max(0.05, Num(o));
                    if (d.TryGetValue("dongu", out o) && o is bool) c.Loop = (bool)o;
                    if (d.TryGetValue("pivot", out o) && o is object[] && ((object[])o).Length == 2) { c.Px = Num(((object[])o)[0]); c.Py = Num(((object[])o)[1]); }
                    if (d.TryGetValue("efekt", out o)) c.Fx = o as string;
                    if (d.TryGetValue("efekt_an", out o)) c.FxAt = Num(o);
                    if (d.TryGetValue("efekt_sure", out o)) c.FxDur = Num(o);
                    if (d.TryGetValue("iz", out o) && o is Dictionary<string, object>)
                        foreach (var tr in (Dictionary<string, object>)o)
                        {
                            var keys = new List<Key>();
                            var arr = tr.Value as object[];
                            if (arr == null) continue;
                            foreach (var k in arr)
                            {
                                var ka = k as object[];
                                if (ka == null || ka.Length < 2) continue;
                                keys.Add(new Key { T = Num(ka[0]), V = Num(ka[1]), Ease = ka.Length > 2 ? ka[2] as string : null });
                            }
                            if (keys.Count > 0) c.Tracks[tr.Key] = keys.OrderBy(k => k.T).ToList();
                        }
                    cs[kv.Key] = c;
                }
            clips = cs;
            triggers = ts;
        }
        catch (Exception ex) { Program.LogError(ex); }
    }

    static double Num(object o) { return Convert.ToDouble(o, CultureInfo.InvariantCulture); }

    public static Clip Get(string name)
    {
        Reload();
        Clip c;
        return name != null && clips.TryGetValue(name, out c) ? c : null;
    }

    static readonly Random rnd = new Random();

    // Tetik adı (done, ifade:sevgi, bekleme...) → klip (tetik yoksa aynı adlı klip, o da yoksa null). Değer virgüllü listeyse ("omuz,salin")
    // her seferinde rastgele biri seçilir.
    public static Clip ForTrigger(string trigger)
    {
        Reload();
        string name;
        if (trigger == null) return null;
        if (!triggers.TryGetValue(trigger, out name)) return Get(trigger); // tetik tanımlı değilse aynı adlı klip
        if (name.Contains(','))
        {
            var opts = name.Split(',').Select(x => x.Trim()).Where(x => x.Length > 0).ToArray();
            name = opts[rnd.Next(opts.Length)];
        }
        return Get(name);
    }

    static double Ease(string e, double u)
    {
        switch (e)
        {
            case "lin": return u;
            case "in": return u * u;
            case "out": return 1 - (1 - u) * (1 - u);
            case "geri": { double c1 = 1.70158, c3 = c1 + 1, v = u - 1; return 1 + c3 * v * v * v + c1 * v * v; } // hedefi biraz geçip döner
            case "sek":
                {
                    // yere düşen top gibi sekerek oturur
                    const double n = 7.5625, d = 2.75;
                    if (u < 1 / d) return n * u * u;
                    if (u < 2 / d) { u -= 1.5 / d; return n * u * u + 0.75; }
                    if (u < 2.5 / d) { u -= 2.25 / d; return n * u * u + 0.9375; }
                    u -= 2.625 / d; return n * u * u + 0.984375;
                }
            default: return 0.5 - 0.5 * Math.Cos(Math.PI * u); // "io": yumuşak başla, yumuşak dur
        }
    }

    static double Track(Clip c, string name, double t, double def)
    {
        List<Key> ks;
        if (!c.Tracks.TryGetValue(name, out ks)) return def;
        if (t <= ks[0].T) return ks[0].V;
        for (int i = 0; i + 1 < ks.Count; i++)
        {
            var a = ks[i]; var b = ks[i + 1];
            if (t > b.T) continue;
            double u = b.T > a.T ? (t - a.T) / (b.T - a.T) : 1;
            return a.V + (b.V - a.V) * Ease(b.Ease, u);
        }
        return ks[ks.Count - 1].V;
    }

    // t: klibin başından beri geçen saniye. Döngü değilse süre bitince son değerde kalır (çağıran bırakır).
    // mirror: sağa/sola yönlü hareketlerde (imlece eğilme) dx ve dönüş ters çevrilir.
    public static Pose Eval(Clip c, double t, bool mirror) { return Eval(c, t, mirror, 1); }

    // gain: genlik çarpanı (sevgi seviyesine göre enerji); kaymalar/dönüş çarpılır, ölçeğin 1'den sapması çarpılır.
    public static Pose Eval(Clip c, double t, bool mirror, double gain)
    {
        var p = Pose.Zero;
        if (c == null) return p;
        if (c.Loop) t = t % c.Dur;
        else t = Math.Min(t, c.Dur);
        double m = mirror ? -1 : 1;
        p.Dx = Track(c, "dx", t, 0) * m * gain;
        p.Dy = Track(c, "dy", t, 0) * gain;
        p.Rot = Track(c, "rot", t, 0) * m * gain;
        p.Sx = 1 + (Track(c, "sx", t, 1) - 1) * gain;
        p.Sy = 1 + (Track(c, "sy", t, 1) - 1) * gain;
        p.Px = c.Px; p.Py = c.Py;
        return p;
    }

    // a'dan b'ye u (0-1) oranında geçiş: durum klibi değişince poz sıçramasın.
    public static Pose Lerp(Pose a, Pose b, double u)
    {
        u = Ease("io", Math.Max(0, Math.Min(1, u)));
        return new Pose { Dx = a.Dx + (b.Dx - a.Dx) * u, Dy = a.Dy + (b.Dy - a.Dy) * u, Rot = a.Rot + (b.Rot - a.Rot) * u,
            Sx = a.Sx + (b.Sx - a.Sx) * u, Sy = a.Sy + (b.Sy - a.Sy) * u, Px = b.Px, Py = b.Py };
    }

    // İki klibin toplamı: kaymalar ve dönüş toplanır, ölçekler çarpılır; pivot üstteki (olay) klibinki.
    public static Pose Combine(Pose a, Pose b)
    {
        return new Pose { Dx = a.Dx + b.Dx, Dy = a.Dy + b.Dy, Rot = a.Rot + b.Rot, Sx = a.Sx * b.Sx, Sy = a.Sy * b.Sy, Px = b.Px, Py = b.Py };
    }

    static readonly Dictionary<string, bool> smoothLooks = new Dictionary<string, bool>();
    // İki poz arasındaki en büyük ekran kayması yarım pikseli geçiyor mu (dönüş başın tepesine göre, ~200 px yarıçap).
    public static bool Moved(Pose a, Pose b, float z)
    {
        double d = Math.Max(Math.Abs(a.Dx - b.Dx), Math.Abs(a.Dy - b.Dy)) * z;
        d = Math.Max(d, Math.Abs(a.Rot - b.Rot) * Math.PI / 180 * 200 * z);
        d = Math.Max(d, Math.Max(Math.Abs(a.Sx - b.Sx), Math.Abs(a.Sy - b.Sy)) * 256 * z);
        return d >= 0.5;
    }

    public static bool Smooth(string look)
    {
        bool v;
        if (!smoothLooks.TryGetValue(look ?? "", out v)) smoothLooks[look ?? ""] = v = look == "yeni" || File.Exists(Path.Combine(Sprites.FramesDir(look), "hairw"));
        return v;
    }

    // Kareyi pozla çizer. Birimler 256 px boyundaki kareye göredir (z ile ölçeklenir).
    // bust: büstün alt kenarı kesik; kalkınca/dönünce boşluk görünmesin diye son satır aşağı uzatılır (pencere keser).
    // Pikselli görünümlerde dönüş/esneme kenarları bozar: yalnız tam piksel kayma uygulanır.
    public static void Draw(Graphics g, Bitmap bmp, RectangleF dest, Pose p, bool bust, bool smooth)
    {
        if (p.Still) { g.DrawImage(bmp, Rectangle.Round(dest)); return; }
        float z = dest.Height / 256f;
        var st = g.Save();
        if (!smooth)
        {
            g.TranslateTransform((float)Math.Round(p.Dx * z), (float)Math.Round(p.Dy * z));
            g.DrawImage(bmp, Rectangle.Round(dest));
            if (bust && p.Dy < 0) g.DrawImage(bmp, new Rectangle((int)dest.X, (int)dest.Bottom, (int)dest.Width, (int)Math.Ceiling(-p.Dy * z) + 1), new Rectangle(0, bmp.Height - 1, bmp.Width, 1), GraphicsUnit.Pixel);
            g.Restore(st);
            return;
        }
        g.InterpolationMode = InterpolationMode.Bilinear; // HighQualityBilinear ön süzgeç yapıyor, ~3 kat yavaş
        g.PixelOffsetMode = PixelOffsetMode.Half;
        float px = dest.X + dest.Width * (float)p.Px, py = dest.Y + dest.Height * (float)p.Py;
        g.TranslateTransform(px + (float)(p.Dx * z), py + (float)(p.Dy * z));
        g.RotateTransform((float)p.Rot);
        g.ScaleTransform((float)p.Sx, (float)p.Sy);
        g.TranslateTransform(-px, -py);
        using (var ia = new ImageAttributes())
        {
            ia.SetWrapMode(WrapMode.TileFlipXY); // kenar pikselleri saydamla karışıp soluklaşmasın
            g.DrawImage(bmp, new[] { new PointF(dest.X, dest.Y), new PointF(dest.Right, dest.Y), new PointF(dest.X, dest.Bottom) },
                new RectangleF(0, 0, bmp.Width, bmp.Height), GraphicsUnit.Pixel, ia);
            if (bust)
            {
                float ext = 48 * z;
                g.DrawImage(bmp, new[] { new PointF(dest.X, dest.Bottom - 1), new PointF(dest.Right, dest.Bottom - 1), new PointF(dest.X, dest.Bottom + ext) },
                    new RectangleF(0, bmp.Height - 1, bmp.Width, 1), GraphicsUnit.Pixel, ia);
            }
        }
        g.Restore(st);
    }

    static void Drop(Graphics g, float x, float y, float r, int a)
    {
        using (var path = new GraphicsPath())
        {
            path.AddBezier(x, y - r * 2.2f, x + r * 0.2f, y - r, x + r, y - r * 0.2f, x + r, y + r * 0.3f);
            path.AddArc(x - r, y - r * 0.7f, 2 * r, 2 * r, 0, 180);
            path.AddBezier(x - r, y + r * 0.3f, x - r, y - r * 0.2f, x - r * 0.2f, y - r, x, y - r * 2.2f);
            using (var b = new SolidBrush(Color.FromArgb(a, 150, 205, 255))) g.FillPath(b, path);
            using (var pen = new Pen(Color.FromArgb(a, Bubble.Ink), 0.32f * r)) g.DrawPath(pen, path);
        }
    }

    // Efektler: t efektin başından beri geçen saniye, dur toplam süre. head: başın tepesi (ekran koordinatı), u: ölçek.
    // loop: durum klibinin efekti (ör. dansta notalar); t sürekli akar, kaybolma yok.
    public static void DrawFx(Graphics g, string fx, double t, double dur, PointF head, float u, bool loop = false)
    {
        if (fx == null || t < 0 || (!loop && t > dur)) return;
        var st = g.Save();
        g.SmoothingMode = SmoothingMode.AntiAlias;
        double fade = loop ? 1 : Math.Min(1, (dur - t) / 0.35); // son 0,35 sn'de kaybolur
        var ink = Bubble.Ink;
        switch (fx)
        {
            case "kalp":
                for (int i = 0; i < 3; i++)
                {
                    double tt = t - i * 0.28;
                    if (tt < 0) continue;
                    double p = Math.Min(1, tt / Math.Max(0.3, dur - 0.56));
                    float x = head.X + (36 + i * 16 - 8) * u + (float)Math.Sin(tt * 5 + i * 2) * 4 * u, y = head.Y + (30 - (float)(p * 46)) * u;
                    float s = (9 + i % 2 * 3) * u * (float)Math.Min(1, tt / 0.15);
                    int a = (int)(255 * Math.Min(fade, 1 - Math.Max(0, p - 0.7) / 0.3));
                    Heart(g, x, y, s, Color.FromArgb(a, 255, 95, 150), Color.FromArgb(a, ink));
                }
                break;
            case "parilti":
                {
                    float[,] at = { { -46, 18 }, { 50, 4 }, { 40, 52 }, { -38, 60 } };
                    for (int i = 0; i < 4; i++)
                    {
                        double ph = (t * 2.2 + i * 0.37) % 1.0;
                        float s = (float)Math.Sin(ph * Math.PI) * (5 + i % 2 * 3) * u;
                        int a = (int)(255 * fade);
                        if (s > 0.5f) Star(g, head.X + at[i, 0] * u, head.Y + at[i, 1] * u, s, Color.FromArgb(a, 255, 236, 140), Color.FromArgb(a, ink));
                    }
                    break;
                }
            case "unlem":
            case "soru":
                {
                    double pop = t < 0.25 ? Ease("geri", t / 0.25) : 1;
                    float s = (float)pop * 36 * u;
                    if (s < 1) break;
                    int a = (int)(255 * fade);
                    float x = head.X + 44 * u, y = head.Y + 4 * u;
                    var gs = g.Save();
                    g.TranslateTransform(x, y);
                    if (fx == "soru") g.RotateTransform((float)(Math.Sin(t * 6) * 8));
                    using (var f = new Font("Segoe UI", s, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (var path = new GraphicsPath())
                    {
                        path.AddString(fx == "soru" ? "?" : "!", f.FontFamily, (int)FontStyle.Bold, s, new PointF(-s * 0.3f, -s * 0.6f), StringFormat.GenericTypographic);
                        using (var pen = new Pen(Color.FromArgb(a, ink), 3 * u) { LineJoin = LineJoin.Round })
                            g.DrawPath(pen, path);
                        using (var b = new SolidBrush(fx == "soru" ? Color.FromArgb(a, 130, 190, 255) : Color.FromArgb(a, 255, 210, 70)))
                            g.FillPath(b, path);
                    }
                    g.Restore(gs);
                    break;
                }
            case "damla":
                {
                    // şakaktan aşağı kayan ter damlası (mahcup/hata)
                    double p = Math.Min(1, t / dur);
                    Drop(g, head.X + 38 * u, head.Y + (34 + (float)(p * 14)) * u, 5 * u, (int)(220 * fade));
                    break;
                }
            case "ofke":
                {
                    // anime öfke damarı: dört kıvrık kol, nabız gibi atar
                    float s = (float)(9 * u * (1 + 0.18 * Math.Max(0, Math.Sin(t * 9))) * (t < 0.2 ? Ease("geri", t / 0.2) : 1));
                    float x = head.X + 40 * u, y = head.Y + 16 * u;
                    int a = (int)(255 * fade);
                    if (s < 0.5f) break;
                    using (var pen = new Pen(Color.FromArgb(a, ink), 5.5f * u) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                    using (var red = new Pen(Color.FromArgb(a, 236, 60, 80), 3f * u) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                        foreach (var pn in new[] { pen, red })
                            for (int q = 0; q < 4; q++)
                            {
                                var gs = g.Save();
                                g.TranslateTransform(x, y);
                                g.RotateTransform(q * 90 + 45);
                                g.DrawArc(pn, s * 0.25f, -s * 0.9f, s * 1.1f, s * 1.1f, 110, 140);
                                g.Restore(gs);
                            }
                    break;
                }
            case "ampul":
                {
                    // fikir ampulü: başın üstünde belirir, ışınları yanıp söner
                    double pop = t < 0.25 ? Ease("geri", t / 0.25) : 1;
                    float r = (float)(9 * u * pop), x = head.X + 6 * u, y = head.Y - 6 * u;
                    if (r < 0.5f) break;
                    int a = (int)(255 * fade);
                    if (t > 0.2 && Math.Sin(t * 14) > -0.3)
                        using (var ray = new Pen(Color.FromArgb(a, 255, 220, 90), 2.2f * u) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                            for (int q = -2; q <= 2; q++)
                            {
                                double ang = q * 0.55 - Math.PI / 2;
                                g.DrawLine(ray, x + (float)Math.Cos(ang) * r * 1.5f, y + (float)Math.Sin(ang) * r * 1.5f, x + (float)Math.Cos(ang) * r * 2.2f, y + (float)Math.Sin(ang) * r * 2.2f);
                            }
                    using (var pen = new Pen(Color.FromArgb(a, ink), 2f * u))
                    using (var glass = new SolidBrush(Color.FromArgb(a, 255, 236, 120)))
                    using (var cap = new SolidBrush(Color.FromArgb(a, 170, 170, 185)))
                    {
                        var capR = new RectangleF(x - r * 0.45f, y + r * 0.8f, r * 0.9f, r * 0.7f);
                        g.FillRectangle(cap, capR); g.DrawRectangle(pen, capR.X, capR.Y, capR.Width, capR.Height);
                        g.FillEllipse(glass, x - r, y - r, 2 * r, 2 * r); g.DrawEllipse(pen, x - r, y - r, 2 * r, 2 * r);
                    }
                    break;
                }
            case "nota":
                {
                    // müzik notaları: her vuruşta (0,5 sn) bir nota sırayla sağdan/soldan yükselip kaybolur
                    for (int q = 0; q < 3; q++)
                    {
                        double beat = t / 0.5 + q, ph = (beat % 3) / 3.0; // 1,5 sn ömür
                        int side = ((int)Math.Floor(beat / 3) + q) % 2 == 0 ? 1 : -1;
                        float x = head.X + side * 62 * u + (float)Math.Sin(ph * 6) * 4 * u, y = head.Y + (60 - (float)ph * 50) * u;
                        int a = (int)(230 * Math.Max(0, Math.Min(1, Math.Min(ph / 0.15, (1 - ph) / 0.3))));
                        float s = 7 * u;
                        using (var path = new GraphicsPath())
                        {
                            path.AddEllipse(x - s * 0.7f, y - s * 0.45f, s * 1.4f, s * 0.95f);
                            path.AddRectangle(new RectangleF(x + s * 0.45f, y - s * 2.4f, s * 0.28f, s * 2.3f));
                            path.AddRectangle(new RectangleF(x + s * 0.45f, y - s * 2.4f, s * 1.0f, s * 0.35f));
                            using (var pen = new Pen(Color.FromArgb(a, ink), 2f * u)) g.DrawPath(pen, path);
                            using (var b = new SolidBrush(side > 0 ? Color.FromArgb(a, 150, 110, 240) : Color.FromArgb(a, 255, 120, 170))) g.FillPath(b, path);
                        }
                    }
                    break;
                }
            case "yildiz":
                {
                    // baş dönmesi: başın etrafında elips üzerinde dönen yıldızlar (arkadakiler küçük)
                    int a = (int)(255 * fade);
                    for (int q = 0; q < 3; q++)
                    {
                        double ang = t * 5 + q * Math.PI * 2 / 3;
                        float x = head.X + (float)Math.Cos(ang) * 52 * u, y = head.Y + 26 * u + (float)Math.Sin(ang) * 11 * u;
                        float s = (float)(9 + 3.5 * Math.Sin(ang)) * u;
                        Star(g, x, y, s, Color.FromArgb(a, 255, 225, 90), Color.FromArgb(a, ink));
                    }
                    break;
                }
        }
        g.Restore(st);
    }

    static void Heart(Graphics g, float x, float y, float s, Color fill, Color line)
    {
        using (var path = new GraphicsPath())
        {
            path.AddBezier(x, y + s * 0.9f, x - s * 1.4f, y - s * 0.1f, x - s * 0.7f, y - s * 1.1f, x, y - s * 0.35f);
            path.AddBezier(x, y - s * 0.35f, x + s * 0.7f, y - s * 1.1f, x + s * 1.4f, y - s * 0.1f, x, y + s * 0.9f);
            using (var b = new SolidBrush(fill)) g.FillPath(b, path);
            using (var pen = new Pen(line, Math.Max(1, s * 0.22f))) g.DrawPath(pen, path);
        }
    }

    static void Star(Graphics g, float x, float y, float s, Color fill, Color line)
    {
        var pts = new PointF[8];
        for (int i = 0; i < 8; i++)
        {
            double a = i * Math.PI / 4;
            float r = i % 2 == 0 ? s : s * 0.32f;
            pts[i] = new PointF(x + (float)(Math.Sin(a) * r), y - (float)(Math.Cos(a) * r));
        }
        using (var b = new SolidBrush(fill)) g.FillPolygon(b, pts);
        using (var pen = new Pen(line, Math.Max(1, s * 0.18f))) g.DrawPolygon(pen, pts);
    }

    // Test/önizleme: Sakura.exe animexport <klip> <klasör> [durum=bekleme] [emote=..] [prefix=idle_] [fps=25] [sure=sn] [ayna=1] [look=..] [hair=#..]
    // Kareleri pencere düzeninde (üstte pay, alt kenar kesik) PNG olarak yazar; sakura-animasyon skill'i GIF'e çevirir.
    public static void Export(string[] args)
    {
        var c = Config.Load();
        string clipName = args.Length > 1 ? args[1] : "bekleme", dir = args.Length > 2 ? args[2] : Path.Combine(Config.Dir, "out", "animasyon", "kare");
        string em = null, prefix = "idle_", state = null;
        double fps = 25, dur = -1;
        bool mirror = false;
        foreach (var a in args.Skip(3))
        {
            var kv = a.Split('=');
            if (kv.Length != 2) continue;
            if (kv[0] == "emote") em = kv[1];
            else if (kv[0] == "look") c.Look = kv[1];
            else if (kv[0] == "prefix") prefix = kv[1];
            else if (kv[0] == "durum") state = kv[1];
            else if (kv[0] == "fps") fps = Num(kv[1]);
            else if (kv[0] == "sure") dur = Num(kv[1]);
            else if (kv[0] == "ayna") mirror = kv[1] == "1";
            else c.Colors[kv[0]] = kv[1];
        }
        var clip = Get(clipName) ?? ForTrigger(clipName);
        var stClip = state != null ? (Get(state) ?? ForTrigger(state)) : null;
        if (clip == null) { Console.Error.WriteLine("klip yok: " + clipName); Environment.Exit(1); }
        if (dur < 0) dur = clip.Dur + (clip.Loop ? 0 : 0.4);
        var frames = new Sprites(c.Look, prefix, em).Render(c.Colors);
        bool bust = !(prefix.StartsWith("stand") || prefix.StartsWith("sit") || prefix.StartsWith("walk"));
        bool smooth = Smooth(c.Look);
        int w = frames.Max(b => b.Width), h = frames.Max(b => b.Height), pad = PadTop(h);
        Directory.CreateDirectory(dir);
        foreach (var old in Directory.GetFiles(dir, "kare_*.png")) File.Delete(old);
        int n = Math.Max(1, (int)Math.Round(dur * fps));
        for (int i = 0; i < n; i++)
        {
            double t = i / fps;
            var cur = frames[(int)(t / 0.14) % frames.Count]; // masaüstündeki gibi 140 ms'de bir kare
            var pose = Eval(clip, t, mirror);
            if (stClip != null) pose = Combine(Eval(stClip, t, false), pose);
            using (var bmp = new Bitmap(w + 40, h + pad, PixelFormat.Format32bppArgb))
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                g.InterpolationMode = InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode = PixelOffsetMode.Half;
                var dest = new RectangleF(20 + (w - cur.Width) / 2, h + pad - cur.Height, cur.Width, cur.Height);
                Draw(g, cur, dest, pose, bust, smooth);
                if (clip.Fx != null) DrawFx(g, clip.Fx, t - clip.FxAt, clip.FxDur, HeadTop(dest, bust, pose), dest.Height / 256f, clip.Loop);
                if (stClip != null && stClip.Fx != null) DrawFx(g, stClip.Fx, t, stClip.FxDur, HeadTop(dest, bust, pose), dest.Height / 256f, true);
                bmp.Save(Path.Combine(dir, string.Format("kare_{0:000}.png", i)), ImageFormat.Png);
            }
        }
        Console.WriteLine(n + " kare → " + dir);
    }

    // Kafanın tepesi: efektler buraya göre konur (pozla birlikte kayar).
    public static PointF HeadTop(RectangleF dest, bool bust, Pose p)
    {
        float z = dest.Height / 256f;
        return bust ? new PointF(dest.X + dest.Width * 0.56f + (float)(p.Dx * z), dest.Y + dest.Height * 0.04f + (float)(p.Dy * z))
                    : new PointF(dest.X + dest.Width * 0.55f + (float)(p.Dx * z), dest.Y + (float)(p.Dy * z));
    }

    // Pencerede kareye üstten bırakılan pay: zıplarken/esnerken başın üstü kesilmesin.
    public static int PadTop(int spriteH) { return Math.Max(10, spriteH / 9); }
}

// Kareleri ve renk grubu haritalarını yükler, menüde seçilen renklere boyar.
class Sprites
{
    class Frame { public int[] Argb; public byte[] Group, HairW, HairS; }
    readonly List<Frame> frames = new List<Frame>();
    public int Width, Height;
    readonly double[] meanL = new double[5], meanS = new double[5];
    // Yeşil saç maskeli görünüm (klasörde "hairw"): grup PNG'sinde G = saç oranı, B = saç gölgesi (HLS açıklığı).
    // Kare saçı varsayılan pembeyle (HairPink) karışık tutar; boyarken kareye oran × (hedef − pembe) eklenir, kenar
    // pikselleri böylece oranında boyanır (saç/ten sınıflandırması yok). smooth.py PINK_* ile aynı olmalı.
    const double PinkH = 345.0 / 360, PinkGain = 1.45, PinkS = 0.62;
    readonly bool weighted;
    double hairMean = 0.5;

    // smooth.py kareleri üretirken klasörde "uretiliyor" işareti olur ve kareler yarı işlenmiştir (ör. saç yeşil):
    // o sırada üretim başında alınan "<look>-onceki" kopyası kullanılır.
    public static string FramesDir(string look)
    {
        string d = Path.Combine(Config.Dir, "frames", look);
        string prev = d + "-onceki";
        return File.Exists(Path.Combine(d, "uretiliyor")) && Directory.Exists(prev) ? prev : d;
    }

    public Sprites(string look, string prefix, string emote)
    {
        string dir = FramesDir(look);
        if (!Directory.Exists(dir)) dir = Path.Combine(Config.Dir, "frames", "klasik");
        weighted = File.Exists(Path.Combine(dir, "hairw"));
        string edir = Path.Combine(dir, "emotes", emote ?? "");
        if (emote != null && Directory.Exists(edir)) dir = edir;
        foreach (var f in Directory.GetFiles(dir, prefix + "*.png").OrderBy(p => p))
        {
            var fr = new Frame { Argb = ReadArgb(f, out Width, out Height) };
            var g = Path.Combine(dir, "groups", Path.GetFileName(f));
            fr.Group = new byte[fr.Argb.Length];
            if (File.Exists(g))
            {
                int gw, gh;
                var ga = ReadArgb(g, out gw, out gh);
                for (int i = 0; i < ga.Length && i < fr.Group.Length; i++) fr.Group[i] = (byte)((ga[i] >> 16) & 0xff);
                if (weighted)
                {
                    fr.HairW = new byte[fr.Argb.Length];
                    fr.HairS = new byte[fr.Argb.Length];
                    for (int i = 0; i < ga.Length && i < fr.HairW.Length; i++) { fr.HairW[i] = (byte)((ga[i] >> 8) & 0xff); fr.HairS[i] = (byte)(ga[i] & 0xff); }
                }
            }
            frames.Add(fr);
        }
        // Her grubun orijinal ortalama açıklık/doygunluğu: yeni renk gölgeleri koruyarak buna göre kaydırılır.
        var n = new int[5];
        var f0 = frames[0];
        for (int i = 0; i < f0.Argb.Length; i++)
        {
            int gi = f0.Group[i];
            if (gi < 1 || gi > 4) continue;
            double h, l, s;
            Hls.From(f0.Argb[i], out h, out l, out s);
            meanL[gi] += l; meanS[gi] += s; n[gi]++;
        }
        for (int gi = 1; gi <= 4; gi++) if (n[gi] > 0) { meanL[gi] /= n[gi]; meanS[gi] /= n[gi]; }
        if (weighted && f0.HairW != null)
        {
            double sum = 0; int cnt = 0;
            for (int i = 0; i < f0.HairW.Length; i++)
                if (f0.HairW[i] >= 128 && ((f0.Argb[i] >> 24) & 0xff) != 0) { sum += f0.HairS[i] / 255.0; cnt++; }
            if (cnt > 0) hairMean = sum / cnt;
        }
    }

    static int[] ReadArgb(string path, out int w, out int h)
    {
        using (var src = new Bitmap(path))
        using (var bmp = new Bitmap(src.Width, src.Height, PixelFormat.Format32bppArgb))
        {
            using (var g = Graphics.FromImage(bmp))
            {
                g.CompositingMode = CompositingMode.SourceCopy;
                g.InterpolationMode = InterpolationMode.NearestNeighbor;
                g.DrawImage(src, new Rectangle(0, 0, src.Width, src.Height));
            }
            w = bmp.Width; h = bmp.Height;
            var data = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
            var arr = new int[w * h];
            Marshal.Copy(data.Scan0, arr, 0, arr.Length);
            bmp.UnlockBits(data);
            return arr;
        }
    }

    public List<Bitmap> Render(Dictionary<string, string> colors)
    {
        var target = new double[5, 3];
        var active = new bool[5];
        for (int gi = 1; gi <= 4; gi++)
        {
            var hex = colors[Config.GroupKeys[gi - 1]];
            if (string.IsNullOrEmpty(hex)) continue;
            Color c;
            try { c = ColorTranslator.FromHtml(hex); } catch { continue; }
            Hls.From(c.ToArgb(), out target[gi, 0], out target[gi, 1], out target[gi, 2]);
            active[gi] = true;
        }
        var outList = new List<Bitmap>();
        foreach (var fr in frames)
        {
            var px = (int[])fr.Argb.Clone();
            for (int i = 0; i < px.Length; i++)
            {
                int gi = fr.Group[i];
                if (fr.HairW != null)
                {
                    if (fr.HairW[i] > 0 && active[1] && ((px[i] >> 24) & 0xff) != 0) px[i] = HairShift(px[i], fr.HairW[i] / 255.0, fr.HairS[i] / 255.0, target);
                    if (gi == 1) continue;
                }
                if (gi < 1 || gi > 4 || !active[gi] || ((px[i] >> 24) & 0xff) == 0) continue;
                double h, l, s;
                Hls.From(px[i], out h, out l, out s);
                // Soluklaştırırken oranla (koyu saç gri-mor kalsın), doygunlaştırırken toplamayla (soluk gözler aşırı parlamasın).
                double ns = target[gi, 2] <= meanS[gi] && meanS[gi] > 0.05 ? s * target[gi, 2] / meanS[gi] : s + (target[gi, 2] - meanS[gi]);
                // Koyulaştırırken oranla: kaydırmayla pembe saçın bütün gölgeleri ve çizgileri sıfıra çakılıp simsiyah
                // bloklar oluyordu; oranla gölgeler gövdeden biraz koyu kalır. Açarken toplamayla (eski davranış).
                // Ortalamadan açık pikseller (parlamalar) kaydırmayla: parlama farkı korunur, saç yassı kütle olmaz.
                bool darken = target[gi, 1] < meanL[gi] && meanL[gi] > 0.05 && l < meanL[gi];
                double nl = darken ? l * target[gi, 1] / meanL[gi] : l + (target[gi, 1] - meanL[gi]);
                px[i] = Hls.To(target[gi, 0], Clamp(nl), Clamp(ns), (px[i] >> 24) & 0xff);
            }
            var bmp = new Bitmap(Width, Height, PixelFormat.Format32bppArgb);
            var data = bmp.LockBits(new Rectangle(0, 0, Width, Height), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
            Marshal.Copy(px, 0, data.Scan0, px.Length);
            bmp.UnlockBits(data);
            outList.Add(bmp);
        }
        return outList;
    }

    // kare = w·P(s) + (1−w)·alttaki  →  yeni = kare + w·(T(s) − P(s)). Gölgeler koyulaştırırken oranla, açarken toplamayla.
    int HairShift(int argb, double w, double s, double[,] target)
    {
        double tl = target[1, 1];
        double nl = tl < hairMean && s < hairMean && hairMean > 0.05 ? s * tl / hairMean : s + (tl - hairMean);
        int t = Hls.To(target[1, 0], Clamp(nl), target[1, 2], 255), p = Hls.To(PinkH, Clamp(s * PinkGain), PinkS, 255);
        int r = Ch(argb, 16, t, p, w), g = Ch(argb, 8, t, p, w), b = Ch(argb, 0, t, p, w);
        return (argb & unchecked((int)0xff000000)) | (r << 16) | (g << 8) | b;
    }

    static int Ch(int px, int sh, int t, int p, double w)
    {
        double v = ((px >> sh) & 0xff) + w * (((t >> sh) & 0xff) - ((p >> sh) & 0xff));
        return v < 0 ? 0 : v > 255 ? 255 : (int)Math.Round(v);
    }

    static double Clamp(double v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
}

static class Hls
{
    public static void From(int argb, out double h, out double l, out double s)
    {
        double r = ((argb >> 16) & 0xff) / 255.0, g = ((argb >> 8) & 0xff) / 255.0, b = (argb & 0xff) / 255.0;
        double max = Math.Max(r, Math.Max(g, b)), min = Math.Min(r, Math.Min(g, b));
        l = (max + min) / 2;
        if (max == min) { h = 0; s = 0; return; }
        double d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        if (max == r) h = (g - b) / d + (g < b ? 6 : 0);
        else if (max == g) h = (b - r) / d + 2;
        else h = (r - g) / d + 4;
        h /= 6;
    }

    public static int To(double h, double l, double s, int a)
    {
        double r, g, b;
        if (s == 0) r = g = b = l;
        else
        {
            double q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
            r = Hue(p, q, h + 1.0 / 3); g = Hue(p, q, h); b = Hue(p, q, h - 1.0 / 3);
        }
        return (a << 24) | ((int)Math.Round(r * 255) << 16) | ((int)Math.Round(g * 255) << 8) | (int)Math.Round(b * 255);
    }

    static double Hue(double p, double q, double t)
    {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1.0 / 6) return p + (q - p) * 6 * t;
        if (t < 0.5) return q;
        if (t < 2.0 / 3) return p + (q - p) * (2.0 / 3 - t) * 6;
        return p;
    }
}

// Saydam, odak çalmayan, her zaman üstte duran pencere tabanı (bildirim ve masaüstü arkadaşı ortak).
// Piksel başına saydamlık (UpdateLayeredWindow): yumuşak kenarlı çizimler hale bırakmadan görünür. Alt sınıfların
// OnPaint'i saydam bir bitmap'e çizilir, Invalidate her seferinde pencereyi yeniler.
class SakuraWindow : Form
{
    protected const int Gap = 4;
    [DllImport("user32.dll")] static extern bool UpdateLayeredWindow(IntPtr hwnd, IntPtr hdcDst, ref Point pptDst, ref Size psize, IntPtr hdcSrc, ref Point pprSrc, int crKey, ref BLENDFUNCTION pblend, int dwFlags);
    [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr h);
    [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr h, IntPtr dc);
    [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleDC(IntPtr dc);
    [DllImport("gdi32.dll")] static extern bool DeleteDC(IntPtr dc);
    [DllImport("gdi32.dll")] static extern IntPtr SelectObject(IntPtr dc, IntPtr obj);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr obj);
    [StructLayout(LayoutKind.Sequential, Pack = 1)] struct BLENDFUNCTION { public byte BlendOp, BlendFlags, SourceConstantAlpha, AlphaFormat; }
    [StructLayout(LayoutKind.Sequential)] struct BITMAPINFOHEADER { public int biSize, biWidth, biHeight; public short biPlanes, biBitCount; public int biCompression, biSizeImage, biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant; }
    [DllImport("gdi32.dll")] static extern IntPtr CreateDIBSection(IntPtr dc, ref BITMAPINFOHEADER bmi, uint usage, out IntPtr bits, IntPtr section, uint offset);
    bool rendering;
    // perftest: son sıfırlamadan beri çizim sayısı ve toplam süresi
    public static int RenderCount;
    public static double RenderMs;
    public static DateTime RenderSince = DateTime.Now;
    // Yeniden kullanılan çizim yüzeyi (DIB): her karede yeni Bitmap + GetHbitmap dönüşümü hareket katmanında
    // (25 kare/sn) tek çekirdeğin dörtte birini yiyordu. GDI+ doğrudan bu belleğe (önceden çarpılmış alfa) çizer.
    IntPtr dibMem, dibBmp, dibOld, dibBits;
    Bitmap dibView;
    Size dibSize;

    void EnsureDib(Size size)
    {
        if (dibView != null && dibSize == size) return;
        FreeDib();
        IntPtr screen = GetDC(IntPtr.Zero);
        dibMem = CreateCompatibleDC(screen);
        ReleaseDC(IntPtr.Zero, screen);
        var bi = new BITMAPINFOHEADER { biSize = Marshal.SizeOf(typeof(BITMAPINFOHEADER)), biWidth = size.Width, biHeight = -size.Height, biPlanes = 1, biBitCount = 32 };
        dibBmp = CreateDIBSection(dibMem, ref bi, 0, out dibBits, IntPtr.Zero, 0);
        dibOld = SelectObject(dibMem, dibBmp);
        dibView = new Bitmap(size.Width, size.Height, size.Width * 4, PixelFormat.Format32bppPArgb, dibBits);
        dibSize = size;
    }

    void FreeDib()
    {
        if (dibView == null) return;
        dibView.Dispose(); dibView = null;
        SelectObject(dibMem, dibOld);
        DeleteObject(dibBmp);
        DeleteDC(dibMem);
    }

    protected override void Dispose(bool disposing) { FreeDib(); base.Dispose(disposing); }

    protected override bool ShowWithoutActivation { get { return true; } }

    protected override CreateParams CreateParams
    {
        get
        {
            var cp = base.CreateParams;
            cp.ExStyle |= 0x08000000 | 0x80 | 0x80000; // WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_LAYERED
            // çerçeve/başlık payı kalmasın: UpdateLayeredWindow pencereyi bitmap boyuna getirir, pay her seferinde düşüp
            // pencere küçülüyordu (büstün üstü kesiliyordu)
            cp.Style = unchecked((int)0x80000000) | (cp.Style & 0x10000000); // WS_POPUP (+ WS_VISIBLE varsa)
            return cp;
        }
    }

    protected override void OnInvalidated(InvalidateEventArgs e) { base.OnInvalidated(e); Render(); }
    [DllImport("user32.dll")] static extern bool ValidateRect(IntPtr h, IntPtr r);
    // Katmanlı pencerenin görüntüsü yalnız UpdateLayeredWindow'dan gelir; WM_PAINT her Invalidate'te sahneyi boşuna
    // ikinci kez (ekran DC'sine) çizdiriyordu.
    protected override void WndProc(ref Message m)
    {
        if (m.Msg == 0x000F) { ValidateRect(m.HWnd, IntPtr.Zero); return; } // WM_PAINT
        base.WndProc(ref m);
    }
    protected override void OnResize(EventArgs e) { base.OnResize(e); Render(); }
    protected override void OnHandleCreated(EventArgs e) { base.OnHandleCreated(e); Render(); }
    protected override void OnVisibleChanged(EventArgs e) { base.OnVisibleChanged(e); if (Visible) Render(); }

    void Render()
    {
        if (!IsHandleCreated || rendering || ClientSize.Width <= 0 || ClientSize.Height <= 0) return;
        rendering = true;
        try
        {
            var sw = Stopwatch.StartNew();
            var size = ClientSize;
            EnsureDib(size);
            using (var g = Graphics.FromImage(dibView))
            {
                g.CompositingMode = CompositingMode.SourceCopy;
                g.Clear(Color.Transparent);
                g.CompositingMode = CompositingMode.SourceOver;
                OnPaint(new PaintEventArgs(g, new Rectangle(Point.Empty, size)));
            }
            IntPtr screen = GetDC(IntPtr.Zero);
            var src = Point.Empty;
            var pos = new Point(Left, Top);
            var bf = new BLENDFUNCTION { BlendOp = 0, BlendFlags = 0, SourceConstantAlpha = 255, AlphaFormat = 1 };
            UpdateLayeredWindow(Handle, screen, ref pos, ref size, dibMem, ref src, 0, ref bf, 2); // ULW_ALPHA
            ReleaseDC(IntPtr.Zero, screen);
            RenderCount++;
            RenderMs += sw.Elapsed.TotalMilliseconds;
        }
        catch (Exception ex) { Program.LogError(ex); }
        finally { rendering = false; }
    }

    protected SakuraWindow()
    {
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
    }

    protected static void PlaySound(Config cfg, string name)
    {
        if (cfg.Muted) return;
        string wav = Path.Combine(Config.Dir, "sounds", name);
        if (File.Exists(wav)) try { new System.Media.SoundPlayer(wav).Play(); } catch { }
    }

    protected static void Pixelated(Graphics g)
    {
        g.InterpolationMode = InterpolationMode.NearestNeighbor;
        g.PixelOffsetMode = PixelOffsetMode.Half;
        g.SmoothingMode = SmoothingMode.None;
    }

    protected ContextMenuStrip BaseMenu(Config cfg, Action dismiss)
    {
        var m = new ContextMenuStrip();
        m.Items.Add("Sakura'yı aç", null, (s, e) => Process.Start(new ProcessStartInfo(Application.ExecutablePath, "menu") { UseShellExecute = false }));
        var mute = new ToolStripMenuItem("Sessize al") { Checked = cfg.Muted, CheckOnClick = true };
        mute.CheckedChanged += (s, e) => { cfg.Muted = mute.Checked; bool v = cfg.Muted; Config.Patch(c => c.Muted = v); };
        m.Items.Add(mute);
        m.Items.Add("1 saat gösterme", null, (s, e) => { cfg.SnoozeUntil = DateTime.Now.AddHours(1); var t = cfg.SnoozeUntil; Config.Patch(c => c.SnoozeUntil = t); dismiss(); });
        return m;
    }
}

// Tek seferlik bildirim: aşağıdan kayarak çıkar, el sallar, kaybolur.
class MascotForm : SakuraWindow
{
    readonly List<Bitmap> frames;
    readonly Event ev;
    readonly Config cfg;
    readonly Size bubble;
    readonly System.Windows.Forms.Timer anim = new System.Windows.Forms.Timer();
    readonly System.Windows.Forms.Timer slide = new System.Windows.Forms.Timer();
    int frame, spriteW, spriteH, targetTop, hiddenTop;
    DateTime shownAt;
    bool leaving;

    public MascotForm(Event ev, Config cfg)
    {
        this.ev = ev;
        this.cfg = cfg;
        var sprites = new Sprites(cfg.Look, ev.Prefix, ev.Emote);
        frames = sprites.Render(cfg.Colors);
        spriteW = sprites.Width * cfg.Scale;
        spriteH = sprites.Height * cfg.Scale;
        bubble = Bubble.Layout(ev);
        ClientSize = new Size(bubble.Width + Gap + spriteW, spriteH);

        var wa = Screen.PrimaryScreen.WorkingArea;
        Left = wa.Right - Width - 8;
        targetTop = wa.Bottom - Height;
        hiddenTop = wa.Bottom;
        Top = hiddenTop;

        anim.Interval = ev.Prefix == "idle_" ? 160 : 90;
        anim.Tick += (s, e) => { frame = (frame + 1) % frames.Count; Invalidate(); };
        slide.Interval = 15;
        slide.Tick += OnSlide;

        MouseClick += (s, e) => { if (e.Button == MouseButtons.Left) { AppFocus.Open(ev.Click); Dismiss(); } };
        ContextMenuStrip = BaseMenu(cfg, Dismiss);
        ContextMenuStrip.Items.Add(new ToolStripSeparator());
        ContextMenuStrip.Items.Add("Kapat", null, (s, e) => Dismiss());
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        shownAt = DateTime.Now;
        anim.Start();
        slide.Start();
        PlaySound(cfg, ev.Sound);
    }

    void OnSlide(object s, EventArgs e)
    {
        int goal = leaving ? hiddenTop : targetTop;
        int step = Math.Max(4, Math.Abs(goal - Top) / 4);
        if (Top == goal)
        {
            if (leaving) { Close(); return; }
            // Uzun metin varsa biraz daha uzun kalsın.
            double secs = cfg.Seconds + Math.Min(4, ev.Body.Length / 30.0);
            if ((DateTime.Now - shownAt).TotalSeconds >= secs && !ContextMenuStrip.Visible) Dismiss();
            return;
        }
        Top = goal > Top ? Math.Min(goal, Top + step) : Math.Max(goal, Top - step);
    }

    void Dismiss() { leaving = true; }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        Pixelated(g);
        g.DrawImage(frames[frame], new Rectangle(bubble.Width + Gap, 0, spriteW, spriteH));
        Bubble.Draw(g, new Rectangle(0, Math.Max(0, spriteH / 5 - bubble.Height / 3), bubble.Width, bubble.Height), ev);
    }
}

// Sakura'nın ana programı: Windows açılınca başlar, saatin yanındaki tepside simgesi durur, mesaj uygulamalarını izler.
// "Masaüstü arkadaşı" açıksa köşede sürekli durur (nefes, göz kırpma, ifade, sürükleme, okşama, sevgi barı);
// kapalıysa görünmeden çalışır ve bildirimleri aşağıdan kayan pencereyle gösterir.
// Claude hook'larından gelen bildirimler WM_COPYDATA ile ulaşır (pencere başlığı "SakuraPet").
class PetForm : SakuraWindow
{
    const string WindowTitle = "SakuraPet";
    const int WM_COPYDATA = 0x004A;
    static readonly string[] Pokes = { "Hı?", "Buradayım!", "Çalışmaya devam!", "Su içmeyi unutma!", "Mola zamanı mı?", "Ehehe~" };
    static readonly string[] LovePokes = { "Seni seviyorum~", "Ehehe~", "Birlikte çalışmak çok güzel!", "Bugün de harikasın!" };
    static readonly string[] LonelyPokes = { "Hı… buradasın demek.", "Uzun zamandır uğramadın…", "Benimle biraz ilgilen…" };
    static readonly string[] Pats = { "Ehehe~", "Hehe, gıdıklanıyor!", "Mmm~", "Daha daha!" };
    static readonly string[] TickleLines = { "Hihihi~ gıdıklanıyorum!", "Ahaha, dur~", "Hihi, orası olmaz!", "Kıkıkı~" };
    static readonly string[] EnoughLines = { "Yeter yeteeer~ nefesim kesildi!", "Tamam tamam, pes ediyorum! Hihi~", "Of… gülmekten yanaklarım ağrıdı~" };
    static readonly string[] AttentionLines = { "Buradayım~", "Hey, beni unuttun mu?", "Biraz da bana bak~", "Ne yapıyorsun? Ben de merak ettim!" };
    static readonly string[] Moods = { "mutlu", "nese", "goz_kirp", "utangac", "gurur" };
    static readonly string[] BreakLines = {
        "{0} dakikadır ekrandasın, kısa bir mola?",
        "Biraz su içmeye ne dersin?",
        "Gözlerini dinlendir: 20 saniye uzağa bak!",
        "Kalkıp biraz gerinmeye ne dersin?",
    };

    [StructLayout(LayoutKind.Sequential)]
    struct COPYDATASTRUCT { public IntPtr dwData; public int cbData; public IntPtr lpData; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, ref COPYDATASTRUCT l);
    [DllImport("user32.dll")] static extern IntPtr PostMessage(IntPtr h, int msg, IntPtr w, IntPtr l);

    readonly Config cfg;
    readonly Random rnd = new Random();
    readonly System.Windows.Forms.Timer anim = new System.Windows.Forms.Timer();
    readonly NotifyIcon tray = new NotifyIcon();
    readonly MessageWatch watch;
    readonly Dictionary<string, DateTime> working = new Dictionary<string, DateTime>();
    readonly List<DateTime> pokeTimes = new List<DateTime>(), turns = new List<DateTime>();
    bool allowShow, dragging, moved, hovering, playing;
    List<Bitmap> idle, current;
    Event ev;              // gösterilen balon (yoksa null)
    DateTime evUntil, moodUntil, nextMood, loveShowUntil, loveTs;
    DateTime lastBreak = DateTime.Now, lastWeatherTry = DateTime.MinValue, lastPat = DateTime.MinValue, lastLonely = DateTime.Now;
    Size bubbleArea = new Size(240, 120);
    int frame, spriteW, spriteH, ticks, love, lastDir, lastMoveX;
    Point dragFrom;
    // hareket katmanı (Anim, anims.json): durum klibi hep döner, olay klibi üstüne bir kez oynar
    int padT;              // pencerede kareye üstten bırakılan pay (zıplarken baş kesilmesin)
    readonly System.Windows.Forms.Timer motionTimer = new System.Windows.Forms.Timer { Interval = 40 };
    readonly DateTime animEpoch = DateTime.Now;
    Anim.Clip shot;        // tek seferlik olay klibi
    DateTime shotAt;
    bool shotMirror;
    Anim.Pose drawnPose = Anim.Pose.Zero; // en son çizilen poz
    DateTime drawnAt;
    double shotGain = 1;   // olay klibinin genliği: sevgi seviyesine göre enerji
    // durum klibi değişince eski pozdan yenisine 0,5 sn'de geçilir (sıçramasın)
    Anim.Clip lastState;
    Anim.Pose lastStatePose = Anim.Pose.Zero, blendFrom = Anim.Pose.Zero;
    DateTime blendAt = DateTime.MinValue;
    // kendi kendine yaşama: kıpırdanma, gece esnemesi, ilgi bekleme
    DateTime nextFidget = DateTime.Now.AddSeconds(45), nextYawn = DateTime.Now.AddMinutes(3), lastTouch = DateTime.Now, lastAttention = DateTime.Now;
    // gıdıklama: art arda tıklamalar; çift tıklama (Claude'u aç) üçüncü tık gelmezse 0,45 sn sonra çalışır
    readonly List<DateTime> clickTimes = new List<DateTime>();
    DateTime dblPendingAt = DateTime.MinValue;
    // hızlı yazma: 100 ms'de bir örnek; girdi olmuş ama imleç kıpırdamamışsa klavye sayılır (tuşlar okunmaz)
    readonly Queue<bool> keySamples = new Queue<bool>();
    uint lastInputTick;
    Point lastSampleCursor;
    DateTime lastSample;
    bool typing;
    bool greeted, farewell, greetPending;
    DateTime visibleAt, lastMotionTick;
    // fırlatılınca takla: pencere uçuş boyunca her yandan büyür (dönen kare kesilmesin)
    int flightPad;
    double spin, settleFrom;
    bool fellHard;                         // son iniş sertti: popo üstüne düştü (yere_dus klibi)
    DateTime standUpAt = DateTime.MaxValue; // oturduğu yerden kalkacağı an
    DateTime settleAt = DateTime.MinValue;
    string song = "";
    // ekran farkındalığı
    string lastVideo = "", seenVideo = "";
    DateTime seenVideoAt, lastVideoReact = DateTime.MinValue;
    bool ytMusic;
    readonly Dictionary<string, DateTime> appReacted = new Dictionary<string, DateTime>();
    string lastFgProcess = "";
    // sistem uyarıları
    FileSystemWatcher downloads;
    bool? online, pluggedIn;
    int netFails, cpuHighCount, ramHighCount, batteryWarnedAt = 101;
    DateTime lastCpuWarn = DateTime.MinValue, lastRamWarn = DateTime.MinValue;
    // konuşma: balon açılınca önce selam (wave_), sonra ağzı oynayan konuşma (talk_), sonra ifadenin bekleme kareleri
    List<Bitmap> evTalk, evIdle;
    int evPhase;           // 0 selam, 1 konuşma, 2 bekleme
    double evTalkSec;
    DateTime talkUntil;
    DateTime voiceAt = DateTime.MaxValue; // Luna'nın sesi bu anda çalar (bildirim sesini kesmesin diye gecikmeli)
    // gezinti: tam boy olup görev çubuğunun üstünde sola yürür, durur ya da oturur, yürüyerek döner
    int roam;              // 0 yok, 1 gidiyor, 2 duruyor/oturuyor, 3 dönüyor
    int homeRight, homeBottom, roamOffset, roamDistance;
    bool draggedRoam;
    double roamPos, walkStep = 120; // walkStep: bir yürüme döngüsünde alınan yol (px), çizilmiş karelerden ölçülür (walk.txt)
    DateTime roamUntil, nextRoam = DateTime.Now.AddMinutes(3);
    List<Bitmap> walkLeft, walkRight, standIdle, sitIdle, thinkFrames;
    List<Bitmap> standTalk, sitTalk; // gezinirken konuşma: tam boy pozun ağzı oynayan kareleri (yoksa null)
    // otururken ifade: sitIdle/sitTalk konuşma süresince ifadenin oturma kareleriyle değişir (emotes/<ifade>/sit-*);
    // asıl kareler burada saklanır. Ayakta poz ifadesiz (yüzü küçük, taşınan ifade bulanıktı).
    List<Bitmap> sitIdleBase, sitTalkBase;
    readonly Dictionary<string, List<Bitmap>[]> sitMoods = new Dictionary<string, List<Bitmap>[]>();
    // pencere üstüne oturma: 4 zıplıyor, 5 pencerenin üstünde, 6 düşüyor (roam değerleri)
    IntPtr perchHwnd;
    int perchDx, dragHomeRight, dragHomeBottom;
    const int PerchSink = 3; // ayaklar başlık çubuğuna biraz gömülsün, havada durmasın
    // uçuş: fırlatma/düşme (yerçekimi, kenarlardan seker) ya da zıplama (iki nokta arası yay)
    class Motion
    {
        public bool Arc, Soft; // Soft: yerden sekmez (havada bırakılınca yumuşak iniş)
        public double X, Y, Vx, Vy, X0, Y0, X1, Y1, H, T; // X, Y: pencerenin sağ alt köşesi
        public DateTime Start, Last;
        public int Bounces;
        public Rectangle Area;
        public Action Land;
    }
    Motion motion;
    DateTime frameAt;
    readonly List<KeyValuePair<DateTime, Point>> dragTrail = new List<KeyValuePair<DateTime, Point>>();
    // uyuklama ve imlece bakma
    bool sleeping, cursorNear;
    DateTime sleptAt, hoverSince, lastGlance = DateTime.MinValue, lastHoverTalk = DateTime.MinValue, nextLook = DateTime.Now.AddSeconds(40);
    readonly Dictionary<string, List<Bitmap>> emoteCache = new Dictionary<string, List<Bitmap>>();
    static readonly string[] WakeLines = { "Hı? Uyumuyordum… sadece gözlerimi dinlendiriyordum~", "Hıh! Geldin mi? *esner*", "Mmh… beş dakika daha…", "Uyandım uyandım! Ehe~" };
    static readonly string[] HoverLines = { "Bana mı bakıyorsun? ~", "İmleç burada ne arıyor? Ehe~", "Utandırıyorsun beni…", "Bir şey mi soracaktın?" };
    static readonly string[] DizzyLines = { "Başım dönüyoor~ @_@", "Dünya dönüyor… ya da ben…", "Bir daha sallama ama!" };
    // sevgi seviyeleri: eşiğe çıkınca kutlama; düşüş için 10 puanlık tampon (sınırda gidip gelmesin)
    static readonly int[] LevelAt = { 0, 25, 50, 80, 100 };
    static readonly string[] LevelNames = { "Küs", "Tanıdık", "Arkadaş", "Yakın arkadaş", "En iyi ev arkadaşı" };
    static readonly string[] LevelUp = { "", "Artık tanışıyoruz sayılır~", "Artık arkadaşız! Ehe~", "Yakın arkadaş olduk! Seninle her şey daha güzel~", "En iyi ev arkadaşım oldun! Bunu kutlamalıyız~" };
    static readonly string[] BestPokes = { "En iyi ev arkadaşımsın, biliyor musun?", "Seninle aynı masaüstünü paylaşmak çok güzel~", "Bugün de buradayım, hep buradayım~" };
    // hava efekti, konfeti, kaçırılan bildirimler, Sakura'ya sor
    string weatherFx = "";
    int weatherTemp;
    DateTime nextWeatherFx = DateTime.Now.AddSeconds(20), fxTestUntil = DateTime.MinValue, confettiFrom = DateTime.MinValue, confettiUntil = DateTime.MinValue;
    readonly List<Event> missed = new List<Event>();
    // Mini (chibi) hâl: video izlerken / oyunda / her zaman köşede küçük oturur, balon çıkarmaz (frames/mini).
    bool mini;
    List<Bitmap> miniLaugh, miniWow;
    int miniHomeRight, miniHomeBottom;   // mini olmadan önceki yer (sağ alt köşe): dönünce oraya
    DateTime miniSeen = DateTime.MaxValue, miniGone = DateTime.MaxValue, miniForceUntil = DateTime.MinValue, nextMiniLife = DateTime.Now;
    const int HotkeyId = 0x5A4B;
    [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr h, int id, int mods, int vk);
    [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr h, int id);
    static readonly string[] OuchLines = { "Ayy! Yavaş ol~", "Uçtum! …ama iniş kötüydü.", "Bu ne hız! Kalbim duracaktı~" };

    public static bool TrySend(Event ev)
    {
        var h = FindWindow(null, WindowTitle);
        if (h == IntPtr.Zero) return false;
        var bytes = Encoding.UTF8.GetBytes(ev.Encode());
        var mem = Marshal.AllocHGlobal(bytes.Length);
        try
        {
            Marshal.Copy(bytes, 0, mem, bytes.Length);
            var cds = new COPYDATASTRUCT { dwData = IntPtr.Zero, cbData = bytes.Length, lpData = mem };
            SendMessage(h, WM_COPYDATA, IntPtr.Zero, ref cds);
            return true;
        }
        finally { Marshal.FreeHGlobal(mem); }
    }

    public static bool IsRunning() { return FindWindow(null, WindowTitle) != IntPtr.Zero; }

    public static void CloseRunning()
    {
        var h = FindWindow(null, WindowTitle);
        if (h != IntPtr.Zero) PostMessage(h, 0x0010, IntPtr.Zero, IntPtr.Zero); // WM_CLOSE
    }

    public PetForm(Config cfg)
    {
        this.cfg = cfg;
        Text = WindowTitle;
        TopMost = cfg.PetTopmost;
        allowShow = cfg.Pet;
        love = cfg.Love;
        loveTs = cfg.LoveTs > 0 ? new DateTime(cfg.LoveTs) : DateTime.Now;
        LoadIdle();
        ClientSize = new Size(bubbleArea.Width + Gap + spriteW, Math.Max(spriteH + padT, bubbleArea.Height));
        var wa = Screen.PrimaryScreen.WorkingArea;
        if (cfg.PetX < 0 || !wa.Contains(cfg.PetX + Width - spriteW / 2, cfg.PetY + Height / 2))
        {
            Left = wa.Right - Width - 8;
            Top = wa.Bottom - Height;
        }
        else { Left = cfg.PetX; Top = cfg.PetY - padT; }
        nextMood = DateTime.Now.AddSeconds(rnd.Next(60, 120));

        MouseDown += (s, e) =>
        {
            lastTouch = DateTime.Now;
            if (sceneNext != null || onArrive != null) { sceneNext = null; onArrive = null; roamUntil = DateTime.Now.AddSeconds(8); }
            // havadayken tutulursa yakalanır
            if (motion != null) { motion = null; EndFlight(); anim.Interval = roam != 0 ? 70 : 140; }
            // gezinirken tutulursa o pozda kalır (yürüyorsa ayakta durur), büste dönmez; pencere üstündeyse sürüklenince iner
            if (roam == 1 || roam == 3 || roam == 4 || roam == 6) { roam = 2; current = standIdle; frame = 0; roamUntil = DateTime.Now.AddSeconds(8); Invalidate(); }
            if (e.Button == MouseButtons.Left) { dragging = true; moved = false; dragFrom = e.Location; dragTrail.Clear(); }
            if (roam == 0) { dragHomeRight = Left + Width; dragHomeBottom = Top + Height; }
        };
        MouseMove += (s, e) =>
        {
            if (!dragging) { DetectPat(e); return; }
            int dx = e.X - dragFrom.X, dy = e.Y - dragFrom.Y;
            if (!moved && Math.Abs(dx) + Math.Abs(dy) < 4) return;
            if (!moved && roam == 5) { roam = 2; current = standIdle; frame = 0; roamUntil = DateTime.Now.AddSeconds(8); }
            if (!moved && roam == 0 && motion == null && !mini && CanRoam()) { moved = true; BeginHold(); return; }
            moved = true;
            Left += dx; Top += dy;
            var now = DateTime.Now;
            dragTrail.Add(new KeyValuePair<DateTime, Point>(now, Cursor.Position));
            dragTrail.RemoveAll(p => (now - p.Key).TotalSeconds > 1.5);
        };
        MouseUp += (s, e) =>
        {
            if (e.Button == MouseButtons.Right) { AppForm.ShowFor(this, ""); return; }
            if (e.Button != MouseButtons.Left) return;
            dragging = false;
            if (mini && moved) { SaveMiniPos(); return; } // mini fırlatılmaz; bırakıldığı yer mini'nin yeri olur
            if (moved && ReleaseThrow()) return;
            if (moved && DropOnWindow()) return;
            if (moved && roam != 0 && Screen.FromControl(this).WorkingArea.Bottom - (Top + Height) > 24) { DropDown(); return; }
            if (moved && roam != 0)
            {
                // bırakıldığı yer yeni evi olur: orada biraz daha durur/oturur, sonra büste döner
                homeRight = Left + Width; homeBottom = Top + Height;
                roamPos = roamOffset = 0;
                draggedRoam = true;
                if (roamUntil < DateTime.Now.AddSeconds(5)) roamUntil = DateTime.Now.AddSeconds(5);
                return;
            }
            if (moved) { int x = Left, y = Top + padT; Config.Patch(c => { c.PetX = x; c.PetY = y; }); return; }
            if (ev != null && ev.Mode != "poke") { AppFocus.Open(ev.Click); BackToIdle(); return; }
            Poke();
        };
        MouseEnter += (s, e) => { hovering = true; hoverSince = DateTime.Now; };
        MouseLeave += (s, e) => hovering = false;
        DoubleClick += (s, e) => dblPendingAt = DateTime.Now; // üçüncü tık gelirse gıdıklamadır, Claude açılmaz

        tray.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        tray.Text = TrayText();
        tray.ContextMenuStrip = BuildMenu();
        tray.MouseClick += (s, e) => { if (e.Button == MouseButtons.Left) AppForm.ShowFor(this, ""); };
        tray.Visible = true;

        watch = new MessageWatch(app => { try { BeginInvoke((Action)(() => OnMessage(app))); } catch { } });
        StartDownloadWatch();
        FormClosed += (s, e) => { tray.Visible = false; tray.Dispose(); watch.Dispose(); if (downloads != null) downloads.Dispose(); };

        anim.Interval = 140;
        anim.Tick += OnTick;
        anim.Start(); // pencere hiç gösterilmese de (arkadaş kapalı) zamanlayıcılar çalışsın
        // akıcı hareket için 25 kare/sn yeniden çizim (kare sırası ve sayaçlar yine anim'de ilerler)
        // Yavaş durum kliplerinde (nefes) poz yarım pikselden az değiştiyse çizilmez: her karede çizmek tek çekirdeğin
        // ~%40'ını yiyordu, hareket katmanı kapalıyken ~%3.
        motionTimer.Tick += (s, e) =>
        {
            if (!Visible || !cfg.AnimOn) return;
            var now = DateTime.Now;
            bool smooth = (now - lastMotionTick).TotalMilliseconds < 80; // arayüz meşgul değil
            lastMotionTick = now;
            if (greetPending && ((smooth && (now - visibleAt).TotalSeconds >= 1.0) || (now - visibleAt).TotalSeconds >= 6))
            {
                greetPending = false;
                if (shot != null && shot.Name == "giris") shotAt = now;
            }
            if ((now - lastSample).TotalMilliseconds >= 100) SampleTyping(now);
            bool settling = (now - settleAt).TotalSeconds < 0.4;
            if (shot == null && !settling && StateClip() == null) return;
            // olay klibi 25 kare/sn; sürekli döngüler (dans dahil) en çok ~16 kare/sn
            if (shot != null || settling || ((now - drawnAt).TotalMilliseconds >= 60 && Anim.Moved(drawnPose, CurrentPose(), spriteH / 256f))) Invalidate();
        };
        // veda: el sallayıp aşağı batar, sonra kapanır (Windows kapanırken beklemez)
        FormClosing += (s, e) =>
        {
            if (farewell || !Visible || !cfg.AnimOn || e.CloseReason == CloseReason.WindowsShutDown || e.CloseReason == CloseReason.TaskManagerClosing) return;
            var bye = Anim.ForTrigger("veda");
            if (bye == null) return;
            e.Cancel = true;
            farewell = true;
            EndRoam();
            motion = null;
            EndFlight();
            ev = null;
            sleeping = false;
            if (!mini && HasFrames(cfg.Look, "wave_", null)) { current = LoadFrames("wave_", null); frame = 0; }
            shot = bye; shotAt = DateTime.Now; shotMirror = false; shotGain = 1;
            var t = new System.Windows.Forms.Timer { Interval = (int)(bye.Dur * 1000) + 100 };
            t.Tick += (a, b) => { t.Stop(); t.Dispose(); Close(); };
            t.Start();
        };
        motionTimer.Start();
    }

    // Arkadaş kapalıyken pencere görünmez ama tutamacı vardır: bildirimler WM_COPYDATA ile yine buraya gelir.
    protected override void SetVisibleCore(bool value)
    {
        if (!allowShow)
        {
            value = false;
            if (!IsHandleCreated) CreateHandle();
        }
        base.SetVisibleCore(value);
    }

    string TrayText() { return "Sakura · sevgi %" + love; }

    // Tepsi simgesine sağ tık: kısa menü. Asıl ayarlar uygulama penceresinde.
    ContextMenuStrip BuildMenu()
    {
        var m = new ContextMenuStrip();
        m.Items.Add("Sakura'yı aç", null, (s, e) => AppForm.ShowFor(this, "home"));
        m.Items.Add("Sohbet", null, (s, e) => AppForm.ShowFor(this, "chat"));
        m.Items.Add("Yapılacaklar", null, (s, e) => AppForm.ShowFor(this, "todo"));
        m.Items.Add("Sakura'ya sor (Ctrl+Shift+Boşluk)", null, (s, e) => AskClipboard(null));
        m.Items.Add(new ToolStripSeparator());
        var mute = new ToolStripMenuItem("Sessize al");
        mute.Click += (s, e) => SetMuted(!cfg.Muted);
        m.Items.Add(mute);
        var voice = new ToolStripMenuItem("Luna konuşsun (ses)");
        voice.Click += (s, e) => { bool v = !cfg.Voice; cfg.Voice = v; Config.Patch(c => c.Voice = v); };
        m.Items.Add(voice);
        var mic = new ToolStripMenuItem("Mikrofon açık (sesli asistan)");
        mic.Click += (s, e) => Jarvis.Set(!Jarvis.On);
        m.Items.Add(mic);
        var cam = new ToolStripMenuItem("Kamera açık (Sakura görsün)");
        cam.Click += (s, e) => Jarvis.SetCam(!Jarvis.CamOn);
        m.Items.Add(cam);
        m.Items.Add("1 saat gösterme", null, (s, e) => SetSnooze(true));
        var shoot = new ToolStripMenuItem("Çekim");
        m.Items.Add(shoot);
        m.Items.Add(new ToolStripSeparator());
        m.Items.Add("Kapat", null, (s, e) => Close());
        m.Opening += (s, e) => { mute.Checked = cfg.Muted; voice.Checked = cfg.Voice; mic.Checked = Jarvis.On; mic.Visible = Jarvis.Installed; cam.Checked = Jarvis.CamOn; cam.Visible = Jarvis.CamInstalled; FillShootMenu(shoot); };
        return m;
    }

    // Uygulama penceresinin kullandıkları.
    public Config Cfg { get { return cfg; } }
    public int Love { get { return love; } }

    public void SetMuted(bool v) { cfg.Muted = v; Config.Patch(c => c.Muted = v); }

    public void SetSnooze(bool on)
    {
        cfg.SnoozeUntil = on ? DateTime.Now.AddHours(1) : DateTime.MinValue;
        var t = cfg.SnoozeUntil;
        Config.Patch(c => c.SnoozeUntil = t);
        if (on) BackToIdle();
    }

    public void SetTopmost(bool v) { cfg.PetTopmost = v; TopMost = v; Config.Patch(c => c.PetTopmost = v); }

    public void SetSmall(bool v) { cfg.PetSmall = v; Config.Patch(c => c.PetSmall = v); RefreshSprite(); }

    public void Preview(Event e) { Notify(e, (int)Math.Ceiling(cfg.Seconds)); }

    // Ayarlar kaydedilince yeniden başlatmadan uygular.
    public void ReloadSettings()
    {
        cfg.CopyFrom(Config.Load());
        Startup.Add();
        RefreshSprite();
    }

    static bool HasMiniFrames() { return File.Exists(Path.Combine(Config.Dir, "frames", "mini", "m0.png")); }

    public void SetMiniAlways(bool v) { cfg.MiniAlways = v; Config.Patch(c => c.MiniAlways = v); UpdateMini(DateTime.Now, true); }
    public void SetMiniVideo(bool v) { cfg.MiniVideo = v; Config.Patch(c => c.MiniVideo = v); UpdateMini(DateTime.Now, true); }
    public void SetMiniGame(bool v) { cfg.MiniGame = v; Config.Patch(c => c.MiniGame = v); UpdateMini(DateTime.Now, true); }

    // ~2 sn'de bir: mini olmalı mı? Tam ekran video/oyun görülünce mini olur, görülmeyince hemen normale döner
    // (Dino 5 Kas: 10 sn beklemek uzun geldi).
    // instant: ayar değişince bekleme yok.
    void UpdateMini(DateTime now, bool instant = false)
    {
        if (farewell || shooting || Desk.IsSetUp || !HasMiniFrames()) { if (mini) SetMini(false, "çekim/kapanış"); return; }
        // Sakura'nın kendisine (mini'ye tıklama, uygulama penceresi) geçince durum değişmesin: tam ekran sanki bitmiş görünür
        if (dragging || (!instant && Screen2.ForegroundIsSelf())) return;
        string why = null, w;
        if (now < miniForceUntil) why = "test";
        else if (cfg.MiniAlways) why = "her zaman";
        else if (cfg.MiniVideo && Screen2.WatchingVideo(out w)) why = "video: " + w;
        else if (cfg.MiniGame && Quiet.GameNow(out w)) why = "oyun: " + w;
        if (why != null)
        {
            miniGone = DateTime.MaxValue;
            if (miniSeen == DateTime.MaxValue) miniSeen = now;
            if (!mini) SetMini(true, why);
        }
        else
        {
            miniSeen = DateTime.MaxValue;
            if (mini && miniGone == DateTime.MaxValue) miniGone = now;
            if (mini) SetMini(false, "video/oyun bitti");
        }
        if (mini) PlaceMini();
    }

    // Mini'nin köşesi: tam ekranda ekranın sağ altı (oynatıcı düğmelerinin üstünde), değilse görev çubuğunun üstü.
    void PlaceMini()
    {
        var scr = Screen.FromPoint(new Point(Left + Width - spriteW / 2, Top + Height - spriteH / 2));
        bool full = Quiet.ForegroundFullscreen();
        var r = full ? scr.Bounds : scr.WorkingArea;
        int dx = cfg.MiniDx >= 0 ? cfg.MiniDx : 16, dy = cfg.MiniDy >= 0 ? cfg.MiniDy : full ? 72 : 0;
        int x = r.Right - dx - Width, y = r.Bottom - dy - Height;
        if (x != Left || y != Top) { Left = x; Top = y; }
    }

    void SaveMiniPos()
    {
        var scr = Screen.FromControl(this);
        var r = Quiet.ForegroundFullscreen() ? scr.Bounds : scr.WorkingArea;
        int dx = Math.Max(0, r.Right - (Left + Width)), dy = Math.Max(0, r.Bottom - (Top + Height));
        cfg.MiniDx = dx; cfg.MiniDy = dy;
        Config.Patch(c => { c.MiniDx = dx; c.MiniDy = dy; });
    }

    void SetMini(bool on, string why)
    {
        if (on == mini) return;
        Program.LogQuiet((on ? "mini oldu: " : "mini bitti: ") + why);
        EndRoam();
        motion = null;
        EndFlight();
        sleeping = false;
        ev = null;
        shot = null;
        thinkFrames = null;
        if (on) { miniHomeRight = Left + Width; miniHomeBottom = Top + Height; }
        mini = on;
        LoadIdle();
        frame = 0;
        bubbleArea = new Size(240, 120);
        ClientSize = new Size(bubbleArea.Width + Gap + spriteW, Math.Max(spriteH + padT, bubbleArea.Height));
        if (on) PlaceMini();
        else { Left = miniHomeRight - Width; Top = miniHomeBottom - Height; nextRoam = DateTime.Now.AddMinutes(rnd.Next(2, 5)); }
        if (cfg.AnimOn && Visible) PlayAnim(on ? "mini_gir" : "mini_cik", false, false);
        Invalidate();
    }

    // Mini hâlde yaşam: arada kafa sallar, kıkırdar; bildirim/dokunma geçici yüz değiştirir.
    void MiniTick(DateTime now)
    {
        if (current != idle && now >= moodUntil) { current = idle; frame = 0; }
        if (cfg.AnimOn && shot == null && !dragging && current == idle && now >= nextMiniLife)
        {
            nextMiniLife = now.AddSeconds(rnd.Next(20, 60));
            int r = rnd.Next(10);
            if (r < 5) PlayAnim("mini_salla", false, false);
            else if (r < 7) MiniFace(miniLaugh, 2.2, "mini_gul");
            else PlayAnim("mini_kipir", rnd.Next(2) == 0, false);
        }
        frame = (frame + 1) % current.Count;
        Invalidate();
    }

    void MiniFace(List<Bitmap> face, double sec, string clip)
    {
        if (face == null) return;
        current = face;
        frame = 0;
        moodUntil = DateTime.Now.AddSeconds(sec);
        if (clip != null) PlayAnim(clip, false, false);
    }

    // Mini hâlde bildirim: balon yok; şaşkın yüz + ünlem + ses. Dokunma/okşama: kıkırdar.
    void MiniReact(Event e, bool sound)
    {
        if (e.Mode == "poke") { MiniFace(miniLaugh, 2.0, "mini_gul"); return; }
        if (sound) PlaySound(cfg, e.Sound);
        MiniFace(miniWow, 2.6, "mini_haber");
    }

    // Görünüm/boyut değişince kareleri yeniden üretir; sağ alt köşe yerinde kalır.
    void RefreshSprite()
    {
        EndRoam();
        roamSet = null;
        sitMoods.Clear(); // eski görünümün ifade kareleri
        motion = null;
        EndFlight();
        sleeping = false;
        thinkFrames = null;
        emoteCache.Clear();
        int right = Left + Width, bottom = Top + Height;
        LoadIdle();
        ev = null;
        frame = 0;
        ClientSize = new Size(bubbleArea.Width + Gap + spriteW, Math.Max(spriteH + padT, bubbleArea.Height));
        Left = right - Width;
        Top = bottom - Height;
        Invalidate();
    }

    public void ChatSay(string ans)
    {
        if (Visible) ShowEvent(new Event { Mode = "poke", Body = ans.Length > 120 ? ans.Substring(0, 118) + "…" : ans, Emote = "mutlu", Prefix = "idle_", Click = null, Sound = "" }, 6);
    }

    // Yapılacaklardan bir iş işaretlenince.
    public void TodoDone(string text)
    {
        AddLove(1, Visible);
        var items = Todos.Load();
        string today = DateTime.Now.ToString("yyyy-MM-dd");
        if (items.Count > 0 && items.All(t => t.Done) && cfg.LastTodoParty != today)
        {
            cfg.LastTodoParty = today;
            Config.Patch(c => c.LastTodoParty = today);
            AddLove(3, Visible);
            Notify(new Event { Mode = "party", Title = "Yapılacaklar", Body = "Hepsini bitirdin, harikasın! Bugünlük listen tertemiz~", Emote = "gurur", Prefix = "wave_", Click = null, Sound = "done.wav" }, 7);
        }
        else Notify(new Event { Mode = "praise", Title = "Yapılacaklar", Body = TodoPraise[rnd.Next(TodoPraise.Length)] + " “" + text + "” bitti.", Emote = "nese", Prefix = "idle_", Click = null, Sound = "" }, 4);
    }

    static readonly string[] TodoPraise = { "Aferin!", "Süpersin!", "Bir iş daha gitti~", "Harika gidiyorsun!" };

    // 12:30 ve 18:00'de (günde birer kez) bitmemiş işleri hatırlatır; uzaktaysan telefona da gider.
    void TodoChecks(DateTime now)
    {
        string today = now.ToString("yyyy-MM-dd");
        bool noon = now.TimeOfDay >= new TimeSpan(12, 30, 0) && now.Hour < 18 && cfg.LastTodoNoon != today;
        bool eve = now.Hour >= 18 && now.Hour < 23 && cfg.LastTodoEve != today;
        if (!noon && !eve) return;
        if (noon) { cfg.LastTodoNoon = today; Config.Patch(c => c.LastTodoNoon = today); }
        else { cfg.LastTodoEve = today; Config.Patch(c => c.LastTodoEve = today); }
        var left = Todos.Load().Where(t => !t.Done).ToList();
        if (left.Count == 0) return;
        string list = string.Join(", ", left.Take(3).Select(t => t.Text)) + (left.Count > 3 ? " …" : "");
        Notify(new Event { Mode = "todo", Title = "Yapılacaklar", Body = "Bugün " + left.Count + " işin kaldı: " + list, Emote = eve ? "utangac" : "saskin", Prefix = "wave_", Click = null, Sound = "ask.wav" }, 9);
    }

    public void SetPetVisible(bool v)
    {
        cfg.Pet = v;
        Config.Patch(c => c.Pet = v);
        allowShow = v;
        if (v) Show(); else Hide();
    }

    void Restart()
    {
        Detached.Start(Application.ExecutablePath, "host --detached --wait");
        Close();
    }

    // Sahne kareleri önbelleği: her balonda ~70 kareyi yeniden boyamak arayüzü 1-3 sn kilitliyordu (müzik sahnesinde
    // sözler şarkılara yetişmiyordu). Sahne başlamadan arka planda doldurulur (WarmScene), sahne bitince boşaltılır;
    // önbellekte olmayan kare her zamanki gibi o an boyanır.
    readonly Dictionary<string, List<Bitmap>> frameCache = new Dictionary<string, List<Bitmap>>();

    string FrameKey(string look, string prefix, string emote)
    {
        return look + "|" + string.Join(",", cfg.Colors.Values) + "|" + cfg.PetSmall + "|" + prefix + "|" + emote;
    }

    List<Bitmap> FramesFor(string look, string prefix, string emote) { return Shrink(new Sprites(look, prefix, emote).Render(cfg.Colors)); }

    List<Bitmap> CachedFrames(string prefix, string emote)
    {
        List<Bitmap> f;
        lock (frameCache) if (frameCache.TryGetValue(FrameKey(cfg.Look, prefix, emote), out f)) return f;
        return FramesFor(cfg.Look, prefix, emote);
    }

    void LoadIdle()
    {
        if (mini)
        {
            // m0 normal, m1 göz kapalı, m2 kahkaha, m3 şaşkın (mini.py). 36 karelik döngüde (5 sn) bir göz kırpar.
            var f = Shrink(new Sprites("mini", "m", null).Render(cfg.Colors));
            idle = Enumerable.Range(0, 36).Select(i => i == 33 || i == 34 ? f[1] : f[0]).ToList();
            miniLaugh = new List<Bitmap> { f[Math.Min(2, f.Count - 1)] };
            miniWow = new List<Bitmap> { f[Math.Min(3, f.Count - 1)] };
            spriteW = f[0].Width;
            spriteH = f[0].Height;
            padT = Anim.PadTop(spriteH);
            current = idle;
            return;
        }
        // Gece yarısından sonra uykulu bekler.
        string mood = DateTime.Now.Hour < 6 ? "uykulu" : null;
        idle = CachedFrames("idle_", mood);
        spriteW = idle[0].Width;
        spriteH = idle[0].Height;
        padT = Anim.PadTop(spriteH);
        current = idle;
    }

    List<Bitmap> Shrink(List<Bitmap> list)
    {
        if (!cfg.PetSmall) return list.Select(Premul).ToList();
        return list.Select(b =>
        {
            var s = new Bitmap(b.Width / 2, b.Height / 2, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(s))
            {
                if (Anim.Smooth(cfg.Look)) { g.InterpolationMode = InterpolationMode.HighQualityBicubic; g.PixelOffsetMode = PixelOffsetMode.HighQuality; }
                else Pixelated(g);
                g.DrawImage(b, new Rectangle(0, 0, s.Width, s.Height));
            }
            b.Dispose();
            return Premul(s);
        }).ToList();
    }

    // GDI+'ın yerel biçimi (önceden çarpılmış alfa): dönen/esneyen kare her çizimde yeniden çevrilmesin.
    static Bitmap Premul(Bitmap b)
    {
        if (b.PixelFormat == PixelFormat.Format32bppPArgb) return b;
        var p = new Bitmap(b.Width, b.Height, PixelFormat.Format32bppPArgb);
        using (var g = Graphics.FromImage(p)) { g.CompositingMode = CompositingMode.SourceCopy; g.DrawImage(b, new Rectangle(0, 0, b.Width, b.Height)); }
        b.Dispose();
        return p;
    }

    static bool HasFrames(string look, string prefix, string emote)
    {
        string dir = Sprites.FramesDir(look);
        if (emote != null && Directory.Exists(Path.Combine(dir, "emotes", emote))) dir = Path.Combine(dir, "emotes", emote);
        return Directory.Exists(dir) && Directory.GetFiles(dir, prefix + "*.png").Length > 0;
    }

    List<Bitmap> LoadFrames(string prefix, string emote) { return Shrink(new Sprites(cfg.Look, prefix, emote).Render(cfg.Colors)); }

    // Gezinti için tam boy kareler bu görünümde var mı (yeni çizim). Çizilmiş yürüme kareleri (walk_) varsa yürür,
    // yoksa olduğu yerde tam boya geçip ayakta durur ya da oturur.
    bool CanRoam() { return HasFrames(cfg.Look, "stand-idle_", null); }

    // dropX/dropY: büst bir pencerenin üst kenarına bırakıldı, oraya otursun (olmazsa false, büst yerinde kalır)
    bool StartRoam(bool perch = false, int dropX = int.MinValue, int dropY = 0)
    {
        if (roam != 0 || !CanRoam()) return false;
        int hr = Left + Width, hb = Top + Height;
        LoadRoamFrames();
        homeRight = hr;
        homeBottom = hb;
        var wa = Screen.FromControl(this).WorkingArea;
        int room = homeRight - spriteW - wa.Left;
        roamDistance = walkRight == null ? 0 : Math.Max(0, Math.Min(room, rnd.Next(300, 700) / (cfg.PetSmall ? 2 : 1)));
        roamOffset = 0;
        roamPos = 0;
        anim.Interval = 70; // gezintide akıcı hareket için daha sık kare
        frame = 0;
        // ara sıra yürümek yerine açık bir pencerenin üst kenarına zıplayıp oturur
        Rectangle wr = Rectangle.Empty;
        bool drop = dropX != int.MinValue;
        IntPtr hw = drop ? Perch.Find(spriteW, PerchNeedH(), out wr, dropX, dropY)
            : perch || rnd.Next(100) < 40 ? Perch.Find(spriteW, PerchNeedH(), out wr) : IntPtr.Zero;
        if (hw == IntPtr.Zero && perch) Program.LogQuiet("perchtest: uygun pencere yok");
        if (hw == IntPtr.Zero && drop) { roam = 2; EndRoam(); return false; }
        if (hw != IntPtr.Zero)
        {
            // kendiliğinden çıkınca sağdaki pencere düğmelerinin (küçült/kapat) üstüne oturmasın
            int lo = 30 + spriteW / 2, hi = Math.Max(lo, wr.Width - 170 - spriteW / 2);
            PlaceRoam();
            PerchOn(hw, wr, drop ? dropX - wr.Left : rnd.Next(lo, hi + 1));
            return true;
        }
        if (walkRight == null) { Arrive(DateTime.Now); PlaceRoam(); return true; }
        roam = 1;
        current = walkLeft;
        PlaceRoam();
        return true;
    }

    // Tam boy kareler (~100 kare, renkle boyanmış): her tutuşta yeniden boyamak bilgisayarı bir saniye kadar kilitliyordu
    // (tutunca Sakura elden kaçıyor, sonra takılıyordu). Görünüm/renk/boy için bir kez hazırlanır; açılıştan biraz sonra
    // arka planda ısıtılır (WarmRoam).
    class RoamSet { public string Key; public List<Bitmap> WalkR, WalkL, Stand, Sit, StandTalk, SitTalk; public double Step; public List<Bitmap>[] Ouch; }
    RoamSet roamSet;
    bool roamWarming;

    string RoamKey() { return cfg.Look + "|" + string.Join(",", cfg.Colors.Values) + "|" + cfg.PetSmall; }

    // Yalnız okur ve yeni kareler üretir (PetForm alanlarına dokunmaz): arka plan iş parçacığında da çalışır.
    RoamSet BuildRoamSet(string key)
    {
        var sw = Stopwatch.StartNew();
        var r = new RoamSet { Key = key, Step = 120 };
        r.WalkR = HasFrames(cfg.Look, "walk_", null) ? LoadFrames("walk_", null) : null;
        // sola yürüme sağdakinin aynası; aynada bozulan aksesuar varsa (bayrak beresinin ay-yıldızı) kendi kareleri walkl_
        r.WalkL = r.WalkR == null ? null : HasFrames(cfg.Look, "walkl_", null) ? LoadFrames("walkl_", null)
            : r.WalkR.Select(b => { var m = (Bitmap)b.Clone(); m.RotateFlip(RotateFlipType.RotateNoneFlipX); return m; }).ToList();
        r.Stand = LoadFrames("stand-idle_", null);
        r.Sit = HasFrames(cfg.Look, "sit-idle_", null) ? LoadFrames("sit-idle_", null) : null;
        r.StandTalk = HasFrames(cfg.Look, "stand-talk_", null) ? LoadFrames("stand-talk_", null) : null;
        r.SitTalk = r.Sit != null && HasFrames(cfg.Look, "sit-talk_", null) ? LoadFrames("sit-talk_", null) : null;
        double st;
        try { if (double.TryParse(File.ReadAllText(Path.Combine(Sprites.FramesDir(cfg.Look), "walk.txt")).Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out st)) r.Step = st; } catch { }
        if (cfg.PetSmall) r.Step /= 2;
        // fırlatılıp popo üstüne düşünce şaşkın oturur: o ifadenin kareleri de hazır olsun (inişte takılmasın)
        if (r.Sit != null && HasFrames(cfg.Look, "sit-idle_", "saskin"))
            r.Ouch = new[] { LoadFrames("sit-idle_", "saskin"), HasFrames(cfg.Look, "sit-talk_", "saskin") ? LoadFrames("sit-talk_", "saskin") : r.SitTalk };
        Program.LogQuiet("tam boy kareler hazırlandı: " + sw.ElapsedMilliseconds + " ms");
        return r;
    }

    void WarmRoam()
    {
        if (roamWarming || roamSet != null || !CanRoam()) return;
        roamWarming = true;
        string key = RoamKey();
        Task.Run(() =>
        {
            RoamSet r = null;
            try { r = BuildRoamSet(key); } catch (Exception ex) { Program.LogError(ex); }
            try { BeginInvoke((Action)(() => { roamWarming = false; if (r != null && roamSet == null && RoamKey() == r.Key) roamSet = r; })); } catch { }
        });
    }

    // Tam boy kareleri (yürüme, ayakta, oturma, konuşma) yükler; sprite alanı en büyüğüne göre büyür.
    void LoadRoamFrames()
    {
        sleeping = false;
        string key = RoamKey();
        if (roamSet == null || roamSet.Key != key) roamSet = BuildRoamSet(key);
        if (!sitMoods.ContainsKey("saskin") && roamSet.Ouch != null) sitMoods["saskin"] = roamSet.Ouch;
        walkRight = roamSet.WalkR;
        walkLeft = roamSet.WalkL;
        standIdle = roamSet.Stand;
        sitIdle = sitIdleBase = roamSet.Sit;
        sitTalk = sitTalkBase = roamSet.SitTalk;
        standTalk = roamSet.StandTalk;
        walkStep = roamSet.Step;
        // tam boy kareler farklı genişlikte: sprite alanı en büyüğüne göre, kare alt-ortaya hizalı çizilir
        var all = (walkRight ?? new List<Bitmap>()).Concat(standIdle).Concat(sitIdle ?? new List<Bitmap>());
        spriteW = all.Max(b => b.Width);
        spriteH = all.Max(b => b.Height);
        ClientSize = new Size(bubbleArea.Width + Gap + spriteW, Math.Max(spriteH + padT, bubbleArea.Height));
    }

    // Büst tutulup kaldırılınca alt kenarı kesik görünüyordu (büst köşede görev çubuğuna yaslı çizilir): tutulduğu an
    // tam boya geçer, imleç göğüs hizasında kalır. Bırakınca pencereye oturur, fırlatılır ya da görev çubuğuna düşer.
    void BeginHold()
    {
        if (ev != null) BackToIdle();
        shot = null;
        var cur = Cursor.Position;
        LoadRoamFrames();
        homeRight = dragHomeRight;
        homeBottom = dragHomeBottom;
        roam = 2;
        current = standIdle;
        frame = 0;
        anim.Interval = 70;
        roamUntil = DateTime.Now.AddSeconds(8);
        int h = standIdle.Max(b => b.Height);
        Left = cur.X - (Width - spriteW / 2);
        Top = cur.Y + (int)(h * 0.78) - Height;
        dragFrom = PointToClient(cur);
        Invalidate();
    }

    // Havada bırakılınca görev çubuğuna düşer; düştüğü yer yeni evi olur (sesli tepki yok, sakin iniş).
    void DropDown()
    {
        roam = 6;
        current = standIdle;
        frame = 0;
        StartMotion(new Motion { X = Left + Width, Y = Top + Height, Soft = true, Land = () =>
        {
            homeRight = Left + Width; homeBottom = Top + Height;
            roamPos = roamOffset = 0;
            draggedRoam = true;
            roam = 2;
            current = standIdle;
            frame = 0;
            roamUntil = DateTime.Now.AddSeconds(6);
        } });
    }

    // Çekim alt menüsü: masaüstünü dekorla kur/geri al, klasör sahneleri (dekor/sahneler.txt başlıkları)
    void FillShootMenu(ToolStripMenuItem shoot)
    {
        shoot.DropDownItems.Clear();
        bool set = Desk.IsSetUp;
        shoot.DropDownItems.Add(set ? "Masaüstünü geri al" : "Masaüstünü çekime hazırla (dekor klasörler)", null, (s, e) => DekorAsync(!set));
        shoot.DropDownItems.Add(new ToolStripSeparator());
        foreach (var sc in Desk.Scenes())
        {
            string name = sc.Key;
            shoot.DropDownItems.Add("Sahne: " + name, null, (s, e) => FolderScene(name));
        }
    }

    // Kurulum ~2 sn sürer (masaüstünün yeni simgeleri görmesi beklenir): ayrı iş parçacığında, bitince balon.
    void DekorAsync(bool setUp)
    {
        var t = new Thread(() =>
        {
            string msg;
            try { msg = setUp ? Desk.Setup() : Desk.Restore(); }
            catch (Exception ex) { Program.LogError(ex); msg = "Olmadı… (" + ex.Message + ")"; }
            BeginInvoke((Action)(() => Say(msg, "mutlu", 4)));
        });
        t.SetApartmentState(ApartmentState.STA);
        t.IsBackground = true;
        t.Start();
    }

    void Say(string text, string emote, int secs, string prefix = "idle_")
    {
        ShowEvent(new Event { Mode = "poke", Body = text, Emote = emote, Prefix = prefix, Click = null, Sound = "" }, secs);
    }

    // Klasör sahnesi (çekim): sıradaki adım ve zamanı; yürüyüş sonu (onArrive). Gezinti biterse ya da dokunulursa iptal.
    Action sceneNext, onArrive;
    DateTime sceneAt, sceneWaitUntil;
    string sceneFolder;
    object sceneDoc;
    List<Desk.Line> sceneLines;

    void SceneAfter(double sec, Action a) { sceneAt = DateTime.Now.AddSeconds(sec); sceneNext = a; }

    // Sahne sözü: yazılı sahneler okunabilsin diye en az 4,5 sn (uzun cümlede daha uzun), sonra sıradaki adım.
    void SceneSay(string key, string fallback, string emote, Action next)
    {
        var l = sceneLines.FirstOrDefault(x => string.Equals(x.Key, key, StringComparison.OrdinalIgnoreCase));
        string text = l != null ? l.Text : fallback;
        if (string.IsNullOrEmpty(text)) { SceneAfter(0.2, next); return; }
        double secs = l != null && l.Secs > 0 ? l.Secs : Math.Max(4.5, Math.Min(10, 2.5 + text.Length / 16.0));
        Say(text, l != null ? l.Emote : emote, (int)Math.Ceiling(secs), key.StartsWith("selam") ? "wave_" : "idle_");
        if (l != null && !string.IsNullOrEmpty(l.Clip)) PlayAnim(l.Clip); // sahnede hareket seçilir (ifadenin rastgele klibi yerine)
        SceneAfter(secs + 0.4, next);
    }

    // Masaüstündeki klasörün simgesine gider (görev çubuğunda yürür, sonra simgenin yanına zıplar), klasörü açar,
    // açılan pencerenin üstüne oturur, içindeki dosyalara sırayla yorum yapar (Explorer'da o dosyayı seçerek), eve döner.
    void FolderScene(string name)
    {
        var talk = Desk.SceneLines(name);
        if (talk.Any(l => l.Key == "tip" && l.Text == "konusma")) { TalkScene(talk); return; }
        Desk.Item icon = null;
        try { icon = Desk.Find(name); } catch (Exception ex) { Program.LogQuiet("sahne: " + ex.Message); }
        if (icon == null || !CanRoam())
        {
            if (roam == 0 && ev == null) Say("Masaüstünde “" + name + "” klasörünü bulamadım~", "saskin", 4);
            return;
        }
        if (ev != null && roam == 0) BackToIdle();
        EndRoam();
        sleeping = false;
        shot = null;
        int hr = Left + Width, hb = Top + Height;
        LoadRoamFrames();
        homeRight = hr;
        homeBottom = hb;
        anim.Interval = 70;
        frame = 0;
        roamPos = roamOffset = 0;
        roamUntil = DateTime.MaxValue;
        sceneFolder = icon.Path;
        sceneLines = Desk.SceneLines(name);
        var wa = Screen.FromControl(this).WorkingArea;
        // simgenin solunda durur (balon onun da solunda açılır); solda yer yoksa sağında
        // ekranın üst kenarındaki simgede başı dışarı taşmasın: o zaman simgenin altında durur
        int right = icon.Rect.Left + 6, bottom = Math.Max(icon.Rect.Bottom - 8, wa.Top + standIdle.Max(b => b.Height) + 4);
        if (right - spriteW - 250 < wa.Left) right = icon.Rect.Right - 6 + spriteW;
        Action jump = () =>
        {
            roam = 4;
            current = standIdle;
            frame = 0;
            JumpTo(right, bottom, () =>
            {
                roam = 2;
                current = standIdle;
                frame = 0;
                roamUntil = DateTime.MaxValue;
                SceneSay("giris", "“" + name + "” mi? Bir bakayım~", "saskin", OpenSceneFolder);
            });
        };
        // görev çubuğunda simgenin hizasına doğru (en çok 500 px) yürür, sonra zıplar
        int walk = homeRight - right;
        if (walkRight != null && walk > 40)
        {
            roamDistance = Math.Min(walk, 500);
            roam = 1;
            current = walkLeft;
            onArrive = jump;
        }
        else roam = 2;
        PlaceRoam();
        if (roam == 2) jump();
    }

    // Konuşma sahnesi (sahneler.txt'de "tip = konusma"): Sakura yerinden kalkmadan sözleri sırayla söyler; anahtarı
    // "selam" ile başlayan söz el sallayarak. Büstteyse büstün kendi ifadeleriyle.
    void TalkScene(List<Desk.Line> lines)
    {
        if (motion != null || dragging) return;
        sleeping = false;
        sceneLines = lines;
        talkScene = true;
        var keys = lines.Where(l => l.Key != "tip").Select(l => l.Key).ToList();
        // gereken kareler: her sözün ifadesi (selam: el sallama), aksesuar takılacaksa o görünümde de
        var need = new List<string[]>();
        string look = cfg.Look;
        need.Add(new[] { look, "idle_", null });
        foreach (var l in lines.Where(x => x.Key != "tip"))
        {
            if (l.Key.StartsWith("!"))
            {
                string nl = SceneLook(l.Key.Substring(1).Split(' ')[0], cfg.Look);
                if (nl != null) { look = nl; need.Add(new[] { look, "idle_", null }); }
                continue;
            }
            need.Add(new[] { look, l.Key.StartsWith("selam") ? "wave_" : "idle_", l.Emote });
            need.Add(new[] { look, "idle_", l.Emote });
            need.Add(new[] { look, "talk_", l.Emote });
        }
        var sw = Stopwatch.StartNew();
        Task.Run(() =>
        {
            foreach (var n in need)
            {
                string k = FrameKey(n[0], n[1], n[2]);
                lock (frameCache) if (frameCache.ContainsKey(k)) continue;
                if (!HasFrames(n[0], n[1], n[2]) && n[2] != null) continue;
                List<Bitmap> f = null;
                try { f = FramesFor(n[0], n[1], n[2]); } catch (Exception ex) { Program.LogError(ex); }
                if (f != null) lock (frameCache) frameCache[k] = f;
            }
        }).ContinueWith(t => BeginInvoke((Action)(() =>
        {
            Program.LogQuiet("sahne kareleri hazır: " + sw.ElapsedMilliseconds + " ms");
            TalkStep(keys, 0);
        })));
    }

    // Konuşma sahnesinde "!" ile başlayan anahtarlar eylemdir (değer: saniye ya da boş):
    //   !spotify = sn   Spotify penceresi kadraja gelir      !oynat = sn   oynat/duraklat tuşu
    //   !sonraki = sn   sonraki şarkı                          !kulaklik = sn  kulaklıklı görünüme geçer (sahne sonunda geri)
    //   !don = sn       dansı o kadar süre keser (donma)       !bekle = sn   bekler
    //   !bere / !gozluk / !kedi = sn  o aksesuarlı görünüm     !sade = sn    aksesuarı çıkarır
    //   !konfeti = sn   konfeti yağar
    //   !sohbet = sn    sahte sohbet penceresi açılır (FakeChat, sahne sonunda kapanır)
    //   !kullanici metin = sn / !asistan metin = sn  hazır mesaj    !yaz metin = sn  kutuya yazılır    !cevap metin = sn  cevap gelir
    void TalkStep(List<string> keys, int i)
    {
        if (i >= keys.Count)
        {
            // sahne bitti: geçici görünüm biraz sonra (kayıt bitince) eski hâline döner
            string lb = lookBefore;
            lookBefore = null;
            SceneAfter(8, () =>
            {
                if (lb != null) { cfg.Look = lb; RefreshSprite(); }
                lock (frameCache) frameCache.Clear();
                if (chat != null) { chat.Close(); chat = null; }
                talkScene = false;
                bubbleArea = new Size(240, 120);
                int h = Math.Max(spriteH + padT, bubbleArea.Height);
                Top += Height - h;
                Height = h;
            });
            return;
        }
        string key = keys[i];
        if (!key.StartsWith("!")) { SceneSay(key, null, "mutlu", () => TalkStep(keys, i + 1)); return; }
        var l = sceneLines.First(x => x.Key == key);
        double sec;
        if (!double.TryParse(l.Text.Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out sec)) sec = 0.5;
        string act = key.Substring(1).Split(' ')[0];
        if (act == "spotify")
        {
            // ekranın sağındaki dikey şeridin üstü (Sakura sağ altta, balonu solunda)
            var wa = Screen.FromControl(this).WorkingArea;
            int strip = wa.Height * 9 / 16;
            if (!Desk.ShowSpotify(new Rectangle(wa.Right - strip + 12, wa.Top + 40, strip - 24, 470))) Program.LogQuiet("sahne: Spotify bulunamadı");
        }
        else if (act == "oynat") Desk.MediaKey(0xB3);
        else if (act == "sonraki") Desk.MediaKey(0xB0);
        else if (act == "don") freezeUntil = DateTime.Now.AddSeconds(sec);
        else if (act == "konfeti") Confetti(6);
        else if (act == "sohbet")
        {
            var wa = Screen.FromControl(this).WorkingArea;
            chat = new FakeChat(new Rectangle(wa.Right - 420, wa.Top + 255, 400, 370));
            chat.Show();
        }
        else if (chat != null && (act == "kullanici" || act == "asistan" || act == "yaz" || act == "cevap"))
        {
            string arg = key.Substring(key.IndexOf(' ') + 1);
            if (act == "yaz") chat.Type(arg);
            else if (act == "cevap") chat.Reply(arg);
            else chat.Add(act == "kullanici", arg);
        }
        else if (SceneLook(act, lookBefore ?? cfg.Look) != null)
        {
            if (lookBefore == null) lookBefore = cfg.Look;
            cfg.Look = SceneLook(act, lookBefore); // config'e yazılmaz: yalnız bu sahne için
            RefreshSprite();
            PlayAnim("ifade:nese");
        }
        SceneAfter(sec, () => TalkStep(keys, i + 1));
    }

    // Aksesuar eylemi ("bere", "gozluk", "kulaklik", "kedi"; "sade" = aksesuarsız) sahne başındaki görünüm
    // "yeni" ise o görünümün adını verir, kareleri yoksa ya da eylem aksesuar değilse null.
    static string SceneLook(string act, string baseLook)
    {
        if (baseLook != "yeni" || !new[] { "bere", "gozluk", "kulaklik", "kedi", "sade" }.Contains(act)) return null;
        string l = act == "sade" ? "yeni" : "yeni-" + act;
        return Directory.Exists(Path.Combine(Config.Dir, "frames", l)) ? l : null;
    }

    FakeChat chat;              // konuşma sahnesinin sahte sohbet penceresi
    string lookBefore;          // konuşma sahnesinde geçici görünümden önceki görünüm
    bool talkScene;             // konuşma sahnesi sürüyor: büyük çekim balonu (Bubble.LayoutFilm), sözün tamamı sesli
    bool shooting;              // çekim masaüstü kurulu (SlowChecks günceller): kendiliğinden göstergeler kapalı
    DateTime freezeUntil;       // "!don": bu ana kadar dans etmez (rickroll'da donup kalma)

    void OpenSceneFolder()
    {
        PlayAnim("zipla");
        try { Process.Start("explorer.exe", "\"" + sceneFolder + "\""); }
        catch (Exception ex) { Program.LogQuiet("sahne: açılamadı " + ex.Message); }
        sceneWaitUntil = DateTime.Now.AddSeconds(6);
        SceneAfter(0.6, WaitSceneWindow);
    }

    // Pencere açılınca Sakura'nın altına yerleştirilir (üstünde oturacak yer kalır), Sakura üstüne zıplar.
    void WaitSceneWindow()
    {
        object doc;
        var hw = Desk.FindExplorer(sceneFolder, out doc);
        if (hw == IntPtr.Zero)
        {
            if (DateTime.Now < sceneWaitUntil) SceneAfter(0.3, WaitSceneWindow);
            else { Say("Açılmadı ki?!", "saskin", 4); roamUntil = DateTime.Now.AddSeconds(6); }
            return;
        }
        sceneDoc = doc;
        var wa = Screen.FromControl(this).WorkingArea;
        // çekim masaüstünde dikey video kadrajı (sağdaki 9:16 şerit, ekran yüksekliği × 9/16) içine sığar
        int strip = wa.Height * 9 / 16;
        int w = Desk.IsSetUp ? Math.Min(strip - 18, wa.Width - 40) : Math.Min(920, wa.Width - 40), h = Desk.IsSetUp ? 520 : 560, sitH = PerchNeedH();
        int cx = Left + Width - spriteW / 2, perchX = w - 170 - spriteW / 2; // sağdaki pencere düğmelerinin solunda oturur
        int top = Math.Min(Math.Max(wa.Top + sitH + 10, Top + Height + 40), wa.Bottom - h - 10);
        int left = Math.Max(wa.Left + 10, Math.Min(wa.Right - w - 10, cx - perchX));
        PlaceSceneWindow(hw, new Rectangle(left, top, w, h), cx, sitH, 0);
    }

    // Explorer açıldıktan hemen sonra kendi hatırladığı boyuta dönebiliyor (yerleştirmeyi eziyor, pencere ekranın
    // tepesinde kalınca Sakura'ya oturacak yer kalmıyordu): pencere istenen yere oturana kadar birkaç kez yerleştirir.
    void PlaceSceneWindow(IntPtr hw, Rectangle want, int cx, int sitH, int tries)
    {
        Desk.PlaceWindow(hw, want);
        SceneAfter(0.45, () =>
        {
            Rectangle wr;
            bool usable = Perch.Usable(hw, spriteW, sitH, out wr);
            bool placed = Math.Abs(wr.Left - want.Left) < 30 && Math.Abs(wr.Top - want.Top) < 30 && Math.Abs(wr.Width - want.Width) < 40;
            if ((!usable || !placed) && tries < 5) { PlaceSceneWindow(hw, want, cx, sitH, tries + 1); return; }
            if (!usable) { Say("Pencereye sığamadım~", "utangac", 4); roamUntil = DateTime.Now.AddSeconds(6); return; }
            PerchOn(hw, wr, cx - wr.Left, () => SceneSay("acinca", null, "dusunce", () => SceneFiles(0)));
        });
    }

    // Klasördeki dosyalara sahneler.txt sırasıyla yorum (dosyası olmayan söz atlanır), sonra "cikis" ve eve dönüş.
    void SceneFiles(int i)
    {
        var files = sceneLines.Where(l => File.Exists(Path.Combine(sceneFolder, l.Key)) || Directory.Exists(Path.Combine(sceneFolder, l.Key))).ToList();
        if (i < files.Count)
        {
            Desk.Select(sceneDoc, files[i].Key);
            SceneSay(files[i].Key, null, "dusunce", () => SceneFiles(i + 1));
            return;
        }
        // son sözden sonra pencereden eve zıplar ve klasörü arkasından kapatır (önce zıplar: oturduğu pencere kapanınca düşmesin)
        SceneSay("cikis", null, "mutlu", () =>
        {
            GoHome(); // zıplarken pencere kontrolü yapılmaz; varınca EndRoam sahneyi bitirir
            Desk.CloseFolder(sceneFolder);
        });
    }

    // Otururken ifadesini değiştirir (null: normal yüz). Oturmuyorsa da kareler hazırlanır, oturunca o yüzle oturur.
    void SetSitMood(string emote)
    {
        if (sitIdleBase == null) return;
        List<Bitmap>[] set = null;
        if (emote != null && !sitMoods.TryGetValue(emote, out set) && HasFrames(cfg.Look, "sit-idle_", emote))
        {
            var idleE = LoadFrames("sit-idle_", emote);
            var talkE = HasFrames(cfg.Look, "sit-talk_", emote) ? LoadFrames("sit-talk_", emote) : sitTalkBase;
            sitMoods[emote] = set = new[] { idleE, talkE };
        }
        var idle = set != null ? set[0] : sitIdleBase;
        var talk = set != null ? set[1] : sitTalkBase;
        if (current == sitIdle) current = idle;
        else if (current == sitTalk && talk != null) current = talk;
        sitIdle = idle;
        sitTalk = talk;
    }

    // Pencerede oturan pozun boyu kadar yer gerekir (ayakta boyu değil)
    int PerchNeedH() { return (sitIdle ?? standIdle).Max(b => b.Height); }

    // Pencerenin üst kenarına zıplar ve oturur; dx: Sakura'nın ortasının pencerenin sol kenarına uzaklığı.
    void PerchOn(IntPtr hw, Rectangle wr, int dx, Action seated = null)
    {
        perchHwnd = hw;
        perchDx = Math.Max(spriteW / 2, Math.Min(wr.Width - spriteW / 2, dx));
        roam = 4;
        current = standIdle;
        frame = 0;
        JumpTo(wr.Left + perchDx + spriteW / 2.0, wr.Top + PerchSink, () =>
        {
            roam = 5;
            current = sitIdle ?? standIdle;
            frame = 0;
            roamUntil = seated != null ? DateTime.MaxValue : DateTime.Now.AddSeconds(rnd.Next(20, 45));
            if (seated != null) seated();
        });
    }

    // Sürükleyip bir pencerenin üst kenarına bırakınca oraya oturur; büstken bırakıldıysa sonra eski köşesine döner.
    bool DropOnWindow()
    {
        if (!CanRoam()) return false;
        int cx = Left + Width - spriteW / 2, by = Top + Height;
        Rectangle wr;
        if (roam == 0)
        {
            // önce ucuz kontrol (kareleri yüklemeden): yakında bir pencere kenarı var mı
            if (Perch.Find(0, 0, out wr, cx, by) == IntPtr.Zero) return false;
            int hr = dragHomeRight, hb = dragHomeBottom;
            if (!StartRoam(false, cx, by)) return false;
            homeRight = hr;
            homeBottom = hb;
            return true;
        }
        var hw = Perch.Find(spriteW, PerchNeedH(), out wr, cx, by);
        if (hw == IntPtr.Zero) return false;
        PerchOn(hw, wr, cx - wr.Left);
        return true;
    }

    void PlaceRoam()
    {
        Left = homeRight - roamOffset - Width;
        Top = homeBottom - Height;
        Invalidate();
    }

    // Gezintiyi bitirir: büste döner, pencere eski yerine (sağ alt köşe) oturur.
    void EndRoam()
    {
        if (roam == 0) return;
        roam = 0;
        sceneNext = null; onArrive = null; sceneDoc = null;
        standUpAt = DateTime.MaxValue;
        motion = null;
        EndFlight();
        anim.Interval = 140;
        LoadIdle();
        ClientSize = new Size(bubbleArea.Width + Gap + spriteW, Math.Max(spriteH + padT, bubbleArea.Height));
        Left = homeRight - Width;
        Top = homeBottom - Height;
        if (draggedRoam) { draggedRoam = false; int x = Left, y = Top + padT; Config.Patch(c => { c.PetX = x; c.PetY = y; }); }
        nextRoam = DateTime.Now.AddMinutes(rnd.Next(4, 10));
        Invalidate();
    }

    // Varınca durur; yarı yarıya yere oturup dinlenir.
    void Arrive(DateTime now)
    {
        roam = 2;
        bool sit = sitIdle != null && rnd.Next(2) == 0;
        current = sit ? sitIdle : standIdle;
        roamUntil = now.AddSeconds(sit ? rnd.Next(15, 30) : rnd.Next(8, 14));
        frame = 0;
    }

    // 70 ms'lik tıklarla: yürüme karesi 2 tıkta bir değişir; bir döngüde (tüm kareler, 2 adım) walkStep kadar yol
    // alınır (walk.txt): ayaklar kaymaz.
    void RoamTick(DateTime now)
    {
        if (sceneNext != null && now >= sceneAt) { var a = sceneNext; sceneNext = null; a(); if (roam == 0 || motion != null) return; }
        double step = walkStep / ((walkRight == null ? 8 : walkRight.Count) * 2);
        if (roam == 1)
        {
            roamPos = Math.Min(roamDistance, roamPos + step);
            roamOffset = (int)roamPos;
            PlaceRoam();
            if (roamOffset >= roamDistance)
            {
                if (onArrive != null) { var a = onArrive; onArrive = null; a(); }
                else Arrive(now);
            }
        }
        else if (roam == 2 && now >= standUpAt)
        {
            standUpAt = DateTime.MaxValue;
            if (current == sitIdle || current == sitTalk) { current = standIdle; frame = 0; PlayAnim("kalkma"); }
        }
        else if (roam == 2 && now >= roamUntil) GoHome();
        else if (roam == 5)
        {
            // pencereyle birlikte hareket eder; pencere kapanır/küçülür/örtülürse düşer
            Rectangle r;
            int cx = Left + Width - spriteW / 2;
            if (!Perch.Still(perchHwnd, spriteW, PerchNeedH(), cx, out r)) { Fall(); return; }
            PlaceAt(r.Left + perchDx + spriteW / 2.0, r.Top + PerchSink);
            if (now >= roamUntil) GoHome();
        }
        else if (roam == 3)
        {
            roamPos = Math.Max(0, roamPos - step);
            roamOffset = (int)roamPos;
            PlaceRoam();
            if (roamOffset == 0) EndRoam();
        }
    }

    // Eve dönüş: aynı hizada ve evin solundaysa yürür, değilse (pencereden, düştüğü yerden) eve zıplar.
    void GoHome()
    {
        int off = homeRight - (Left + Width);
        bool level = Math.Abs(Top + Height - homeBottom) < 4;
        if (level && off == 0) { EndRoam(); return; }
        if (level && off > 0 && walkRight != null)
        {
            roamPos = off;
            roam = 3;
            current = walkRight;
            frame = 0;
            return;
        }
        roam = 4;
        current = standIdle;
        frame = 0;
        JumpTo(homeRight, homeBottom, EndRoam);
    }

    void Fall()
    {
        roam = 6;
        current = standIdle;
        StartMotion(new Motion { X = Left + Width, Y = Top + Height, Land = () =>
        {
            roam = 2;
            current = standIdle;
            frame = 0;
            roamUntil = DateTime.Now.AddSeconds(5);
            ShowEvent(new Event { Mode = "poke", Body = "Ayy! Pencere nereye gitti?!", Emote = "saskin", Prefix = "idle_", Click = null, Sound = "" }, 3);
        } });
    }

    void StartMotion(Motion m)
    {
        m.Start = m.Last = DateTime.Now;
        if (m.Area.IsEmpty) m.Area = Screen.FromControl(this).WorkingArea;
        motion = m;
        anim.Interval = 20;
    }

    void JumpTo(double x1, double y1, Action land)
    {
        double x0 = Left + Width, y0 = Top + Height, d = Math.Sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0));
        StartMotion(new Motion { Arc = true, X = x0, Y = y0, X0 = x0, Y0 = y0, X1 = x1, Y1 = y1, H = 60 + Math.Max(0, y0 - y1) * 0.5, T = Math.Max(0.45, Math.Min(1.0, d / 1400)), Land = land });
    }

    void PlaceAt(double right, double bottom)
    {
        Left = (int)Math.Round(right) - Width + flightPad;
        Top = (int)Math.Round(bottom) - Height + flightPad;
        Invalidate();
    }

    void StepMotion(DateTime now)
    {
        var m = motion;
        if (m.Arc)
        {
            // x düzgün, y doğru + parabol: hedefe tam iner
            double t = Math.Min(1, (now - m.Start).TotalSeconds / m.T);
            m.X = m.X0 + (m.X1 - m.X0) * t;
            m.Y = m.Y0 + (m.Y1 - m.Y0) * t - 4 * m.H * t * (1 - t);
            PlaceAt(m.X, m.Y);
            if (t >= 1) FinishMotion();
            return;
        }
        double dt = Math.Min(0.05, (now - m.Last).TotalSeconds);
        m.Last = now;
        m.Vy += 3200 * dt;
        m.X += m.Vx * dt;
        // takla atmaz: gittiği yöne en çok 15° eğilir (dönerken kare kesiliyor, garip görünüyordu); duvardan sekince eğim döner
        if (flightPad > 0) spin += (Math.Max(-15, Math.Min(15, m.Vx / 60)) - spin) * Math.Min(1, dt * 10);
        m.Y += m.Vy * dt;
        var wa = m.Area;
        if (m.X > wa.Right) { m.X = wa.Right; m.Vx = -m.Vx * 0.6; }
        if (m.X - spriteW < wa.Left) { m.X = wa.Left + spriteW; m.Vx = -m.Vx * 0.6; }
        if (m.Y - spriteH < wa.Top) { m.Y = wa.Top + spriteH; m.Vy = Math.Abs(m.Vy) * 0.5; }
        if (m.Y >= wa.Bottom)
        {
            m.Y = wa.Bottom;
            if (!m.Soft && m.Vy > 700 && m.Bounces < 2) { m.Vy = -m.Vy * 0.35; m.Vx *= 0.6; m.Bounces++; }
            else { PlaceAt(m.X, m.Y); FinishMotion(); return; }
        }
        PlaceAt(m.X, m.Y);
    }

    void FinishMotion()
    {
        var m = motion;
        motion = null;
        EndFlight();
        anim.Interval = roam != 0 ? 70 : 140;
        if (m.Land != null) m.Land();
        if (roam != 0) PlayAnim(fellHard ? "yere_dus" : "inis");
        fellHard = false;
    }

    // Bırakırken: son ~0,1 sn hızlıysa fırlar; çok sallandıysa başı döner. Bir şey yaptıysa true.
    bool ReleaseThrow()
    {
        var now = DateTime.Now;
        var recent = dragTrail.Where(p => (now - p.Key).TotalMilliseconds <= 100).ToList();
        double vx = 0, vy = 0;
        if (recent.Count >= 2 && (now - recent[recent.Count - 1].Key).TotalMilliseconds < 60)
        {
            double sec = Math.Max(0.016, (recent[recent.Count - 1].Key - recent[0].Key).TotalSeconds);
            vx = (recent[recent.Count - 1].Value.X - recent[0].Value.X) / sec;
            vy = (recent[recent.Count - 1].Value.Y - recent[0].Value.Y) / sec;
        }
        // sallama: 1,5 sn içinde en az 4 kez (her biri ≥25 px) yön değiştirdiyse
        int turnsN = 0, dir = 0;
        double run = 0;
        for (int i = 1; i < dragTrail.Count; i++)
        {
            int d = dragTrail[i].Value.X - dragTrail[i - 1].Value.X;
            if (d == 0) continue;
            int sd = Math.Sign(d);
            if (sd != dir) { if (dir != 0 && run >= 25) turnsN++; dir = sd; run = 0; }
            run += Math.Abs(d);
        }
        bool dizzy = turnsN >= 4;
        double speed = Math.Sqrt(vx * vx + vy * vy);
        dragTrail.Clear();
        if (speed >= 1300)
        {
            double cap = Math.Min(1, 4000 / speed);
            Fling(vx * cap, vy * cap, dizzy);
            return true;
        }
        if (!dizzy) return false;
        if (roam == 0) { int x = Left, y = Top + padT; Config.Patch(c => { c.PetX = x; c.PetY = y; }); }
        else { homeRight = Left + Width; homeBottom = Top + Height; roamPos = roamOffset = 0; draggedRoam = true; }
        ShowEvent(new Event { Mode = "poke", Body = DizzyLines[rnd.Next(DizzyLines.Length)], Emote = "saskin", Prefix = "idle_", Click = null, Sound = "" }, 4);
        PlayAnim("bas_donmesi");
        return true;
    }

    void Fling(double vx, double vy, bool dizzy)
    {
        sleeping = false;
        if (ev != null && ev.Mode == "poke") ev = null;
        if (roam == 0) { current = EmoteFrames("saskin"); frame = 0; }
        else { roam = 6; current = standIdle; frame = 0; }
        var mo = new Motion { X = Left + Width, Y = Top + Height, Vx = vx, Vy = vy };
        mo.Land = () =>
        {
            var say = new Event { Mode = "poke", Body = dizzy ? DizzyLines[rnd.Next(DizzyLines.Length)] : OuchLines[rnd.Next(OuchLines.Length)], Emote = "saskin", Prefix = "idle_", Click = null, Sound = "" };
            if (roam == 0) { int x = Left, y = Top + padT; Config.Patch(c => { c.PetX = x; c.PetY = y; }); }
            else
            {
                // düştüğü yer yeni evi olur (sürükleyip bırakmak gibi)
                homeRight = Left + Width; homeBottom = Top + Height;
                roamPos = roamOffset = 0;
                draggedRoam = true;
                roam = 2;
                // yerden sektiyse popo üstüne düşer, biraz oturur, sonra kalkar (yeni çizim gerekmez: oturma pozu)
                fellHard = mo.Bounces > 0 && sitIdle != null;
                current = fellHard ? sitIdle : standIdle;
                if (fellHard) { spin = 0; standUpAt = DateTime.Now.AddSeconds(1.8); }
                frame = 0;
                roamUntil = DateTime.Now.AddSeconds(fellHard ? 7 : 6);
            }
            ShowEvent(say, 3);
            if (dizzy) PlayAnim("bas_donmesi");
        };
        StartMotion(mo);
        if (cfg.AnimOn) { spin = 0; SetFlightPad((int)(Math.Max(spriteW, spriteH) * 0.35)); }
    }

    // Yana bakış kareleri (emotes/bak_sol, bak_sag) var mı
    bool HasLook() { return Directory.Exists(Path.Combine(Sprites.FramesDir(cfg.Look), "emotes", "bak_sol")); }

    List<Bitmap> EmoteFrames(string emote)
    {
        List<Bitmap> f;
        if (!emoteCache.TryGetValue(emote, out f)) emoteCache[emote] = f = LoadFrames("idle_", emote);
        return f;
    }

    void FallAsleep()
    {
        sleeping = true;
        sleptAt = DateTime.Now;
        current = EmoteFrames("uykulu");
        frame = 0;
        Invalidate();
    }

    // Ağız ve ses aynı süreyi kullanır. Sahnede sözün tamamı okunur (video sesi de tamamını kullanıyor), masaüstünde ilk 3 sn.
    double VoiceMax { get { return talkScene ? 30 : 3; } }
    double TalkSeconds(Event e) { return e.Mode == "jarvis" ? jarvisTalk : Math.Max(0.6, Voice.Seconds(e.Body, e.Emote, VoiceMax)); }

    // Sesli asistan (sakura-araclar\jarvis): sesi Python servisi çalar; burada yalnızca balon, ifade ve ağız.
    // Title = durum (dinliyor | dusunuyor | konusuyor | bitti), Footer = konuşmanın saniyesi.
    double jarvisTalk;
    void JarvisEvent(Event e)
    {
        if (e.Title == "bitti") { if (ev != null && ev.Mode == "jarvis") BackToIdle(); return; }
        double sec;
        if (!double.TryParse(e.Footer, NumberStyles.Float, CultureInfo.InvariantCulture, out sec)) sec = 0;
        jarvisTalk = sec;
        string body = e.Body.Length > 160 ? e.Body.Substring(0, 158) + "…" : e.Body;
        var je = new Event { Mode = "jarvis", Body = body, Emote = string.IsNullOrEmpty(e.Emote) ? "mutlu" : e.Emote, Prefix = "idle_", Click = null, Sound = "" };
        // konuşurken balon sözden 2 sn fazla kalır; dinleme/düşünme balonu bir sonraki duruma kadar (en çok 60 sn)
        ShowEvent(je, e.Title == "konusuyor" ? (int)Math.Ceiling(sec + 2) : 60);
    }

    void ShowEvent(Event e, int seconds)
    {
        if (mini) { MiniReact(e, false); return; } // mini balon çıkarmaz
        sleeping = false;
        if (roam != 0 && e.Mode == "poke")
        {
            // gezinirken dokunma/okşama/sohbet: pozunu bozmadan (yürüyorsa durup) balonla cevap verir
            if (roam == 1 || roam == 3) { roam = 2; current = standIdle; frame = 0; }
            ev = e;
            bubbleArea = Bubble.Layout(e);
            int need = bubbleArea.Width + Gap + spriteW;
            if (need > Width) { int right = Left + Width; Width = need; Left = right - Width; } // Sakura yerinde kalsın
            evUntil = DateTime.Now.AddSeconds(seconds);
            if (roamUntil < evUntil.AddSeconds(3)) roamUntil = evUntil.AddSeconds(3);
            SetSitMood(e.Emote);
            // ayakta ya da otururken balonun okunuş süresi kadar ağzı oynar (kare sırası aynı, nefes kesintisiz)
            var talkSet = current == standIdle ? standTalk : current == sitIdle ? sitTalk : null;
            if (talkSet != null)
            {
                current = talkSet;
                talkUntil = DateTime.Now.AddSeconds(0.1 + TalkSeconds(e));
            }
            voiceAt = DateTime.Now.AddSeconds(0.1);
            PlayEventAnim(e);
            Invalidate();
            return;
        }
        EndRoam(); // gezinirken bildirim gelirse yerine döner
        ev = e;
        bubbleArea = talkScene ? Bubble.LayoutFilm(e) : Bubble.Layout(e);
        int needW = bubbleArea.Width + Gap + spriteW;
        if (needW > Width) { Left -= needW - Width; Width = needW; }
        if (talkScene)
        {
            // pencere yukarı doğru büyür, Sakura yerinde kalır (kare alttan hizalı)
            int needH = bubbleArea.Height + spriteH + flightPad;
            if (needH > Height) { Top -= needH - Height; Height = needH; }
        }
        current = CachedFrames(e.Prefix, e.Emote);
        evIdle = e.Prefix == "idle_" ? current : CachedFrames("idle_", e.Emote);
        evTalk = HasFrames(cfg.Look, "talk_", e.Emote) ? CachedFrames("talk_", e.Emote) : null;
        // ses ne kadar sürüyorsa ağız o kadar oynar; bildirim sesi varsa Luna'nın sesi gecikmeli başlar
        evTalkSec = TalkSeconds(e);
        double voiceDelay = string.IsNullOrEmpty(e.Sound) ? 0.1 : 0.9;
        evPhase = e.Prefix == "wave_" ? 0 : 1;
        if (evPhase == 1 && evTalk != null) current = evTalk;
        talkUntil = DateTime.Now.AddSeconds(voiceDelay + evTalkSec);
        voiceAt = evPhase == 1 ? DateTime.Now.AddSeconds(voiceDelay) : DateTime.MaxValue;
        frame = 0;
        evUntil = DateTime.Now.AddSeconds(seconds);
        PlayEventAnim(e);
        Invalidate();
    }

    // Olay klibi: bildirimlerde olay türü (done, msg, ask...) önce gelir, ifade rastgeledir; dokunma/okşama gibi
    // "poke" olaylarında ifade (ifade:sevgi = okşama, ifade:saskin = fırlatma) türü belirler.
    void PlayEventAnim(Event e)
    {
        if (e.Mode == "poke") { if (!PlayAnim("ifade:" + e.Emote)) PlayAnim("poke"); }
        else if (!PlayAnim(e.Mode)) PlayAnim("ifade:" + e.Emote);
    }

    // energetic: genlik sevgi seviyesine göre (küsken ağır, en iyi arkadaşken canlı); giriş/veda/gerinme sabit.
    bool PlayAnim(string trigger, bool mirror = false, bool energetic = true)
    {
        if (!cfg.AnimOn || farewell) return false;
        // giriş bitmeden başka klip araya girmesin (açılışta hemen gelen şarkı yorumu onu eziyordu)
        if (shot != null && shot.Name == "giris" && (DateTime.Now - shotAt).TotalSeconds < shot.Dur) return false;
        var c = Anim.ForTrigger(trigger);
        if (c == null) return false;
        shot = c; shotAt = DateTime.Now; shotMirror = mirror;
        shotGain = energetic ? Energy() : 1;
        return true;
    }

    double Energy() { return new[] { 0.6, 0.8, 1.0, 1.15, 1.3 }[Math.Max(0, Math.Min(4, Level()))]; }

    // Hızlı yazıyor mu: son 3 sn'deki 30 örneğin en az 12'sinde klavye girdisi (bırakmak için 6'nın altı).
    void SampleTyping(DateTime now)
    {
        lastSample = now;
        uint t = Activity.LastInputTick();
        var c = Cursor.Position;
        keySamples.Enqueue(t != lastInputTick && c == lastSampleCursor);
        lastInputTick = t;
        lastSampleCursor = c;
        while (keySamples.Count > 30) keySamples.Dequeue();
        int n = keySamples.Count(b => b);
        typing = typing ? n >= 6 : n >= 12;
    }

    // Uçuş payı: dönen kare pencereden taşmasın diye pencere sağdan, alttan ve üstten büyür; kare ekranda yerinde kalır.
    void SetFlightPad(int p)
    {
        if (p == flightPad) return;
        int right = Left + Width - flightPad, bottom = Top + Height - flightPad;
        ClientSize = new Size(ClientSize.Width - flightPad + p, ClientSize.Height - 2 * flightPad + 2 * p);
        flightPad = p;
        Left = right - Width + p;
        Top = bottom - Height + p;
        Invalidate();
    }

    // Uçuş bitti: pencere eski boyuna döner, kalan takla açısı 0,4 sn'de en yakın düz duruşa döner.
    void EndFlight()
    {
        if (flightPad == 0 && spin == 0) return;
        double a = ((spin % 360) + 540) % 360 - 180;
        if (Math.Abs(a) > 1) { settleFrom = a; settleAt = DateTime.Now; }
        spin = 0;
        SetFlightPad(0);
    }

    // Sürekli dönen durum klibi; yürürken/uçarken yok (o anların kendi hareketi var).
    Anim.Clip StateClip()
    {
        if (!cfg.AnimOn || roam == 1 || roam == 3 || roam == 4 || roam == 6 || motion != null || dragging || farewell) return null;
        if (mini) return Anim.ForTrigger("mini_bekleme") ?? Anim.ForTrigger("bekleme");
        if (roam != 0) return Anim.ForTrigger("bekleme_boy");
        if (sleeping) return Anim.ForTrigger("uyku");
        if (typing && ev == null) { var ty = Anim.ForTrigger("yaziyor"); if (ty != null) return ty; }
        if (playing && (ev == null || ev.Mode == "poke") && DateTime.Now >= freezeUntil) return Anim.ForTrigger("muzik");
        if (weatherFx != "" && ev == null) { var w = Anim.ForTrigger("hava:" + weatherFx); if (w != null) return w; }
        if (working.Count > 0 && ev == null && !shooting) return Anim.ForTrigger("calisiyor") ?? Anim.ForTrigger("bekleme");
        return Anim.ForTrigger("bekleme");
    }

    Anim.Pose CurrentPose()
    {
        var now = DateTime.Now;
        Anim.Pose p;
        if (motion != null && !motion.Arc && flightPad > 0)
            p = new Anim.Pose { Sx = 1, Sy = 1, Px = 0.5, Py = 0.5, Rot = spin }; // fırlatılmış: ortasından takla atar
        else
        {
            var st = StateClip();
            p = Anim.Eval(st, (now - animEpoch).TotalSeconds, false);
            if (st != lastState) { blendFrom = lastStatePose; blendAt = now; lastState = st; }
            double bt = (now - blendAt).TotalSeconds;
            if (bt < 0.5) p = Anim.Lerp(blendFrom, p, bt / 0.5);
            lastStatePose = p;
            double sb = (now - settleAt).TotalSeconds;
            if (sb < 0.4) { p.Rot += settleFrom * (1 + Math.Cos(Math.PI * sb / 0.4)) / 2; p.Px = 0.5; p.Py = 0.5; }
        }
        if (shot != null)
        {
            double t = (now - shotAt).TotalSeconds;
            if (t > Math.Max(shot.Dur, shot.Fx != null ? shot.FxAt + shot.FxDur : 0) || dragging || (motion != null && roam == 0 && !farewell)) shot = null;
            else if (t <= shot.Dur) p = Anim.Combine(p, Anim.Eval(shot, t, shotMirror, shotGain));
        }
        return p;
    }

    protected override void OnVisibleChanged(EventArgs e)
    {
        // merhaba: ilk görünüşte aşağıdan çıkıp zıplar
        if (Visible && !greeted && cfg.AnimOn && PlayAnim("giris", false, false))
        {
            // açılışta kareler hazırlanırken arayüz bir süre meşgul: o sırada aşağıda gizli bekler (t<0 → ilk anahtar),
            // hareket zamanlayıcısı rahat çalışmaya başlayınca yükselir
            greeted = true;
            greetPending = true;
            shotAt = DateTime.MaxValue;
            visibleAt = DateTime.Now;
        }
        base.OnVisibleChanged(e);
    }

    // Boşta kendi kendine yaşar: sabah gerinme, gece esneme, uzun süre ilgilenilmezse dikkat çekme, ara sıra kıpırdanma.
    void IdleLife(DateTime now)
    {
        bool present = Activity.IdleSeconds() < 60;
        string today = now.ToString("yyyy-MM-dd");
        if (now.Hour >= 5 && present && cfg.LastStretch != today && current == idle)
        {
            cfg.LastStretch = today;
            Config.Patch(c => c.LastStretch = today);
            PlayAnim("gerin", false, false);
            return;
        }
        if (now.Hour < 6 && now >= nextYawn && current == idle)
        {
            nextYawn = now.AddMinutes(rnd.Next(4, 10));
            current = EmoteFrames("uykulu");
            frame = 0;
            moodUntil = now.AddSeconds(3.5);
            PlayAnim("esne", false, false);
            return;
        }
        if (present && working.Count == 0 && Level() > 0 && (now - lastTouch).TotalMinutes >= 45 && (now - lastAttention).TotalMinutes >= 45)
        {
            lastAttention = now;
            ShowEvent(new Event { Mode = "poke", Body = AttentionLines[rnd.Next(AttentionLines.Length)], Emote = "nese", Prefix = "wave_", Click = null, Sound = "" }, 4);
            PlayAnim("dikkat");
            return;
        }
        if (now >= nextFidget)
        {
            nextFidget = now.AddSeconds(rnd.Next(35, 90) / Energy());
            if (current == idle || current == thinkFrames) PlayAnim("kipir");
        }
    }

    // Arkadaş görünürse balonla, değilse aşağıdan kayan ayrı pencereyle gösterir.
    MascotForm popup;            // arkadaş kapalıyken gösterilen tek kayan pencere
    Event pending;               // tam ekran sırasında gelen son önemli bildirim (bitince gösterilir)
    DateTime pendingAt;
    bool quietHidden;

    // Arkadaş görünürse balonla, değilse aşağıdan kayan pencereyle gösterir. Aynı anda tek Sakura olur:
    // yeni bildirim eski kayan pencerenin yerini alır. Tam ekran (oyun) sırasında ses çalmaz, ekrana bir şey
    // çıkarmaz; önemli bildirimi saklar ve tam ekrandan çıkınca gösterir.
    void Notify(Event e, int seconds)
    {
        bool chatter = e.Mode == "song" || e.Mode == "poke" || e.Mode == "screen";
        bool hidden = quietHidden || Quiet.ShouldHide(cfg);
        Phone.Maybe(cfg, e, hidden);
        // uzaktayken (5 dk dokunulmadı ya da tam ekran) gelen önemli bildirimler dönünce özetlenir
        if ((hidden || mini || Activity.IdleSeconds() >= 300) && (e.Mode == "msg" || e.Mode == "done" || e.Mode == "ask" || e.Mode == "error" || e.Mode == "reminder"))
            missed.Add(e);
        if (hidden)
        {
            if (!chatter) { pending = e; pendingAt = DateTime.Now; }
            return;
        }
        if (mini && Visible)
        {
            // video izlerken: yorum yok; önemli bildirimde balonsuz tepki, ayrıntısı normale dönünce ("Sen yokken" / bekleyen)
            if (!chatter) { pending = e; pendingAt = DateTime.Now; MiniReact(e, true); }
            return;
        }
        if (roam != 0 && chatter) return; // gezinirken ekran/şarkı yorumu gezintiyi bölmesin
        if (Visible) { ShowEvent(e, seconds); PlaySound(cfg, e.Sound); return; }
        if (chatter) return;
        if (popup != null && !popup.IsDisposed) popup.Close();
        popup = new MascotForm(e, cfg);
        popup.Show();
    }

    // Kare listesi değiştiğinde sayaç da sıfırlanmalı: el sallama 20, bekleme 12 kare.
    void BackToIdle()
    {
        ev = null;
        current = idle;
        frame = 0;
        Invalidate();
    }

    void AddLove(int d, bool show)
    {
        love = Math.Max(0, Math.Min(100, love + d));
        int l = love; long ts = loveTs.Ticks; // loveTs azalma saatidir; artış onu sıfırlamaz
        Config.Patch(c => { c.Love = l; c.LoveTs = ts; });
        if (show) loveShowUntil = DateTime.Now.AddSeconds(4);
        tray.Text = TrayText();
        CheckLevel(show);
    }

    int Level()
    {
        int lv = cfg.LoveLevel;
        if (lv < 0) { lv = 0; for (int i = 0; i < LevelAt.Length; i++) if (love >= LevelAt[i]) lv = i; }
        while (lv < LevelAt.Length - 1 && love >= LevelAt[lv + 1]) lv++;
        while (lv > 0 && love < LevelAt[lv] - 10) lv--;
        return lv;
    }

    // Seviye değiştiyse kaydeder; yükselişte konfetiyle kutlar, düşüşte (gösterilebiliyorsa) küser.
    void CheckLevel(bool show)
    {
        int old = cfg.LoveLevel, lv = Level();
        if (lv == old) return;
        cfg.LoveLevel = lv;
        Config.Patch(c => c.LoveLevel = lv);
        if (old < 0 || !Visible || Quiet.ShouldHide(cfg)) return;
        if (lv > old)
        {
            Confetti(6);
            // dokunma/okşama balonundan sonra gelsin (aynı anda çağrılıyor)
            var up = new Event { Mode = "party", Title = "Sevgi: " + LevelNames[lv], Body = LevelUp[lv], Emote = "sevgi", Prefix = "wave_", Click = null, Sound = "done.wav" };
            BeginInvoke((Action)(() => Notify(up, 7)));
        }
        else if (show || ev == null)
            Notify(new Event { Mode = "poke", Title = "Sevgi: " + LevelNames[lv], Body = lv == 0 ? "Hıh. Küstüm sana…" : "Beni biraz ihmal ettin gibi…", Footer = "Başımı okşayabilirsin", Emote = "uzgun", Prefix = "idle_", Click = null, Sound = "" }, 6);
    }

    void Confetti(double seconds) { confettiFrom = DateTime.Now; confettiUntil = confettiFrom.AddSeconds(seconds); }

    void Poke()
    {
        var now = DateTime.Now;
        // gıdıklama: 2,5 sn'de 4 tık kıkırdatır; 5 sn'de 8 tık "yeter" dedirtir
        clickTimes.Add(now);
        clickTimes.RemoveAll(t => (now - t).TotalSeconds > 5);
        if (cfg.AnimOn && clickTimes.Count >= 8)
        {
            clickTimes.Clear();
            dblPendingAt = DateTime.MinValue;
            ShowEvent(new Event { Mode = "poke", Body = EnoughLines[rnd.Next(EnoughLines.Length)], Emote = "utangac", Prefix = "idle_", Click = null, Sound = "" }, 3);
            PlayAnim("yeter");
            return;
        }
        if (cfg.AnimOn && clickTimes.Count(t => (now - t).TotalSeconds <= 2.5) >= 4)
        {
            dblPendingAt = DateTime.MinValue;
            ShowEvent(new Event { Mode = "poke", Body = TickleLines[rnd.Next(TickleLines.Length)], Emote = "nese", Prefix = "idle_", Click = null, Sound = "" }, 3);
            PlayAnim("gidik");
            return;
        }
        pokeTimes.RemoveAll(t => (now - t).TotalMinutes > 10);
        pokeTimes.Add(now);
        if (pokeTimes.Count <= 3) AddLove(2, true);
        string[] lines = Level() == 4 && rnd.Next(2) == 0 ? BestPokes : love >= 80 ? LovePokes : love <= 25 ? LonelyPokes : Pokes;
        string emote = love <= 25 ? "utangac" : Moods[rnd.Next(Moods.Length)];
        ShowEvent(new Event { Mode = "poke", Body = lines[rnd.Next(lines.Length)], Emote = emote, Prefix = "idle_", Click = null, Sound = "" }, 3);
    }

    // Okşama: imleç başın üstünde 1,5 saniye içinde en az 4 kez sağa sola gidip gelirse.
    void DetectPat(MouseEventArgs e)
    {
        int sx = Width - spriteW - flightPad, sy = Height - spriteH - flightPad;
        if (e.X < sx || e.Y > sy + spriteH * 45 / 100) return;
        var now = DateTime.Now;
        int dir = Math.Sign(e.X - lastMoveX);
        lastMoveX = e.X;
        if (dir == 0 || dir == lastDir) return;
        lastDir = dir;
        turns.Add(now);
        turns.RemoveAll(t => (now - t).TotalSeconds > 1.5);
        if (turns.Count >= 4 && (now - lastPat).TotalSeconds > 5)
        {
            lastPat = now;
            lastTouch = now;
            turns.Clear();
            AddLove(5, true);
            ShowEvent(new Event { Mode = "poke", Body = Pats[rnd.Next(Pats.Length)], Emote = "sevgi", Prefix = "idle_", Click = null, Sound = "" }, 3);
        }
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == 0x0312 && m.WParam.ToInt32() == HotkeyId) { BeginInvoke((Action)(() => AskClipboard(null))); return; } // WM_HOTKEY
        if (m.Msg == WM_COPYDATA)
        {
            var cds = (COPYDATASTRUCT)Marshal.PtrToStructure(m.LParam, typeof(COPYDATASTRUCT));
            var bytes = new byte[cds.cbData];
            Marshal.Copy(cds.lpData, bytes, 0, cds.cbData);
            var e = Event.Decode(Encoding.UTF8.GetString(bytes));
            BeginInvoke((Action)(() => OnEvent(e)));
            m.Result = (IntPtr)1;
            return;
        }
        base.WndProc(ref m);
    }

    void OnEvent(Event e)
    {
        // Çalışan Claude oturumlarını izle: "work" düşünme hâlini başlatır, bitiş/hata o oturumu kapatır.
        if (e.Mode == "open") { AppForm.ShowFor(this, e.Body); return; }
        if (e.Mode == "roam") { StartRoam(); return; } // test: Sakura.exe roamtest
        if (e.Mode == "mini") { int sec; int.TryParse(e.Body, out sec); miniForceUntil = sec > 0 ? DateTime.Now.AddSeconds(sec) : DateTime.MinValue; UpdateMini(DateTime.Now, true); return; } // test: Sakura.exe minitest [sn]
        if (e.Mode == "sahne") { FolderScene(e.Body); return; } // Sakura.exe sahnetest <klasör> ya da tepsi → Çekim
        if (e.Mode == "perch") { StartRoam(true); return; }
        if (e.Mode == "love") { loveShowUntil = DateTime.Now.AddSeconds(8); Invalidate(); return; }
        if (e.Mode == "weather") { fxTestUntil = DateTime.Now.AddMinutes(2); SetWeatherFx(e.Body == "clear" ? "" : e.Body, 35, true); return; }
        if (e.Mode == "confetti") { Confetti(6); return; }
        if (e.Mode == "close") { Close(); return; }
        if (e.Mode == "perf")
        {
            // Sakura.exe perftest: önceki perftest'ten beri saniyede kaç çizim, çizim başına kaç ms (quiet.log)
            double sec = (DateTime.Now - RenderSince).TotalSeconds;
            var stc = StateClip();
            Program.LogQuiet(string.Format(CultureInfo.InvariantCulture, "perftest: {0:0.0} sn, {1:0.0} çizim/sn, çizim başına {2:0.00} ms, durum={3}, olay={4}, müzik={5}",
                sec, RenderCount / Math.Max(0.1, sec), RenderMs / Math.Max(1, RenderCount), stc == null ? "-" : stc.Name, shot == null ? "-" : shot.Name, playing));
            RenderCount = 0; RenderMs = 0; RenderSince = DateTime.Now;
            return;
        }
        if (e.Mode == "anim")
        {
            var parts = (e.Body ?? "").Split(' ');
            var c = Anim.Get(parts[0]);
            if (c != null) { shot = c; shotAt = DateTime.Now; shotMirror = parts.Length > 1 && parts[1] == "ayna"; shotGain = 1; }
            else if (!PlayAnim(parts[0], parts.Length > 1 && parts[1] == "ayna")) Program.LogQuiet("animtest: klip/tetik yok: " + parts[0]);
            Invalidate();
            return;
        }
        if (e.Mode == "missed") { missed.Add(EventBuilder.Build("msg", new[] { "msg", "whatsapp" }, "", cfg)); missed.Add(EventBuilder.Build("msg", new[] { "msg", "whatsapp" }, "", cfg)); missed.Add(new Event { Mode = "done" }); ShowMissed(); return; }
        if (e.Mode == "ask") { AskClipboard(e.Body); return; }
        if (e.Mode == "jarvis") { JarvisEvent(e); return; }
        if (e.Mode == "drop" && roam == 0)
        {
            var xy = e.Body.Split(',');
            dragHomeRight = Left + Width; dragHomeBottom = Top + Height;
            Left = int.Parse(xy[0]) + spriteW / 2 - Width; Top = int.Parse(xy[1]) - Height;
            if (!DropOnWindow()) { Left = dragHomeRight - Width; Top = dragHomeBottom - Height; Program.LogQuiet("droptest: pencere kenarı yok"); }
            return;
        }
        if (e.Mode == "sleep") { if (roam == 0) { ev = null; FallAsleep(); } return; }
        if (e.Mode == "fling") { if (roam == 0) Fling(-1800, -1400, true); return; }
        if (e.Mode == "work")
        {
            bool fresh = working.Count == 0;
            working[e.Session] = DateTime.Now;
            if (fresh && ev == null && roam == 0) PlayAnim("fikir"); // yeni iş: aklına bir fikir gelir
            Invalidate();
            return;
        }
        bool bigDone = false; // 10 dk'dan uzun süren iş bitti: konfetili kutlama
        if (e.Mode == "done" || e.Mode == "error")
        {
            DateTime started;
            if (e.Mode == "done" && !string.IsNullOrEmpty(e.Session) && working.TryGetValue(e.Session, out started) && (DateTime.Now - started).TotalMinutes >= 10) bigDone = true;
            if (string.IsNullOrEmpty(e.Session)) working.Clear(); else working.Remove(e.Session);
        }
        if (e.Mode == "done") AddLove(1, false); // birlikte iş bitirmek de sevindirir
        cfg.Muted = Config.Load().Muted;
        Notify(e, (int)Math.Ceiling(cfg.Seconds + Math.Min(4, e.Body.Length / 30.0)));
        if (bigDone && ev == e && PlayAnim("kutlama")) Confetti(3);
    }

    void OnMessage(string app)
    {
        var c = Config.Load();
        if (c.SnoozeUntil > DateTime.Now) return;
        cfg.Muted = c.Muted;
        var e = EventBuilder.Build("msg", new[] { "msg", app }, "", c);
        Notify(e, (int)Math.Ceiling(cfg.Seconds + 1));
    }

    // Sesli asistan bekçisi (sakura-araclar\jarvis): açılışta ve uykudan dönünce asistan kapalıysa yeniden başlatır.
    // Dino "Sakura Sustur" ile kapattıysa (kapali.flag) dokunmaz. Asistan çalışırken 127.0.0.1:47621'i dinler.
    DateTime nextJarvisCheck = DateTime.Now.AddSeconds(45), lastJarvisStart = DateTime.MinValue;
    void JarvisWatch(DateTime now)
    {
        if (now < nextJarvisCheck) return;
        nextJarvisCheck = now.AddSeconds(30);
        string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "sakura-araclar", "jarvis");
        string py = Path.Combine(Path.GetDirectoryName(dir), "ses", "venv_xtts", "Scripts", "pythonw.exe");
        if (!File.Exists(Path.Combine(dir, "sakura_asistan.py")) || !File.Exists(py) || File.Exists(Path.Combine(dir, "kapali.flag"))) return;
        if ((now - lastJarvisStart).TotalMinutes < 3) return; // açılması ~1,5 dk sürer; çöküyorsa sık sık denemesin
        try { using (var c = new System.Net.Sockets.TcpClient()) { if (c.ConnectAsync("127.0.0.1", 47621).Wait(500)) return; } }
        catch { } // bağlanamadı: asistan kapalı
        lastJarvisStart = now;
        Program.LogQuiet("asistan kapalıydı, başlatılıyor");
        Process.Start(new ProcessStartInfo(py, "\"" + Path.Combine(dir, "sakura_asistan.py") + "\"") { WorkingDirectory = dir, UseShellExecute = false, CreateNoWindow = true });
    }

    // Her ~2 saniyede bir: Spotify, mola, hava durumu, gün sonu özeti ve sevgi.
    void SlowChecks(DateTime now)
    {
        try { JarvisWatch(now); } catch (Exception ex) { Program.LogError(ex); }
        foreach (var key in working.Where(kv => (now - kv.Value).TotalHours > 2).Select(kv => kv.Key).ToList()) working.Remove(key);

        if (cfg.Spotify && Visible)
        {
            string title = SpotifyNow.Title();
            bool nowPlaying = title != null;
            if (nowPlaying && title != song && ev == null && !Desk.IsSetUp)
            {
                var parts = title.Split(new[] { " - " }, 2, StringSplitOptions.None);
                string artist = parts.Length == 2 ? parts[0] : "", name = parts.Length == 2 ? parts[1] : title;
                var r = Screen2.SongReaction(artist, name);
                var sev = new Event { Mode = "song", Title = "♪ " + name + (artist != "" ? " – " + artist : ""), Body = r[0], Emote = r[1], Prefix = "idle_", Click = "spotify", Sound = "" };
                ShowEvent(sev, 5);
                AiRewrite(sev, "Kullanıcı şu an Spotify'da şu şarkıyı dinliyor: “" + name + "”" + (artist != "" ? ", sanatçı: " + artist : "") + ".");
            }
            if (nowPlaying) song = title;
            playing = nowPlaying;
        }
        else playing = false;
        playing |= ytMusic;

        double idleSec = Activity.IdleSeconds();
        shooting = Desk.IsSetUp;
        bool quiet = cfg.SnoozeUntil > now || Quiet.ShouldHide(cfg) || shooting || mini; // çekimde bildirim yok; mini: video izlerken sessiz
        foreach (var text in Reminders.TakeDue())
            Notify(new Event { Mode = "reminder", Title = "Hatırlatma", Body = text, Emote = "saskin", Prefix = "wave_", Click = null, Sound = "ask.wav" }, 12);
        TodoChecks(now);
        if (cfg.ScreenAware && Visible && !quiet) ScreenChecks(now);
        else ytMusic = false;
        if (cfg.SystemAlerts && !quiet) SystemChecks(now);
        if (idleSec >= 300) lastBreak = now; // 5 dk uzak kaldıysa mola vermiş sayılır
        if (cfg.BreakMinutes > 0 && ev == null && !quiet && idleSec < 60 && (now - lastBreak).TotalMinutes >= cfg.BreakMinutes)
        {
            lastBreak = now;
            Stats.Log("break", "", 0);
            Notify(new Event { Mode = "break", Title = "Mola zamanı", Body = string.Format(BreakLines[rnd.Next(BreakLines.Length)], cfg.BreakMinutes), Emote = "utangac", Prefix = "idle_", Click = null, Sound = "ask.wav" }, 8);
        }

        string today = now.ToString("yyyy-MM-dd");
        if (cfg.City != "" && cfg.LastWeather != today && now.Hour >= 6 && now.Hour < 12 && idleSec < 60 && !quiet && (now - lastWeatherTry).TotalMinutes >= 10)
        {
            lastWeatherTry = now;
            Task.Run(() => Weather.Morning(cfg)).ContinueWith(t =>
            {
                if (t.Status != TaskStatus.RanToCompletion || t.Result == null) return;
                BeginInvoke((Action)(() =>
                {
                    cfg.LastWeather = today;
                    Config.Patch(c => c.LastWeather = today);
                    Notify(t.Result, 9);
                }));
            });
        }

        if (now.Hour >= 20 && cfg.LastSummary != today && idleSec < 60 && !quiet && ev == null && Stats.Today().Done > 0)
        {
            cfg.LastSummary = today;
            Config.Patch(c => c.LastSummary = today);
            Notify(Stats.TodaySummary(false), 10);
        }

        if (missed.Count > 0 && idleSec < 3 && !quiet) ShowMissed();
        if (cfg.City != "" && now >= nextWeatherFx && now >= fxTestUntil) WeatherFxCheck(now);
        if (Visible && ev == null && !quiet && idleSec < 60) SpecialDays(now);

        // Sevgi saatte 5 puan azalır; çok düşükse ara sıra ilgi ister.
        int hours = (int)(now - loveTs).TotalHours;
        if (hours >= 1)
        {
            love = Math.Max(0, love - 5 * hours);
            loveTs = loveTs.AddHours(hours);
            int l = love; long ts = loveTs.Ticks;
            Config.Patch(c => { c.Love = l; c.LoveTs = ts; });
            tray.Text = TrayText();
            CheckLevel(false);
        }
        if (love <= 25 && Visible && ev == null && !quiet && idleSec < 60 && (now - lastLonely).TotalHours >= 2)
        {
            lastLonely = now;
            ShowEvent(new Event { Mode = "poke", Body = "Biraz ilgilen benimle…", Footer = "Başımı okşayabilirsin", Emote = "uzgun", Prefix = "idle_", Click = null, Sound = "" }, 6);
        }
    }

    // "Sen yokken" özeti: uygulamaya göre sayılar; mesaj varsa tıklayınca son mesajın uygulaması açılır.
    void ShowMissed()
    {
        var parts = new List<string>();
        string click = null;
        foreach (var grp in missed.Where(m => m.Mode == "msg").GroupBy(m => m.Title))
        {
            parts.Add(grp.Key + ": " + grp.Count() + " mesaj"); // "'tan/'dan" eki uygulamaya göre değişir, iki nokta hep doğru
            click = grp.Last().Click;
        }
        int done = missed.Count(m => m.Mode == "done"), ask = missed.Count(m => m.Mode == "ask"), err = missed.Count(m => m.Mode == "error"), rem = missed.Count(m => m.Mode == "reminder");
        if (done > 0) parts.Add("Claude " + done + " işi bitirdi");
        if (ask > 0) parts.Add("Claude " + ask + " kez seni bekledi");
        if (err > 0) parts.Add(err + " hata");
        if (rem > 0) parts.Add(rem + " hatırlatma");
        missed.Clear();
        if (parts.Count == 0) return;
        Notify(new Event { Mode = "missed", Title = "Sen yokken", Body = string.Join(", ", parts) + ".", Footer = ask + err > 0 ? "Claude'a bakmak ister misin?" : "", Emote = "mutlu", Prefix = "wave_", Click = click ?? (ask + err + done > 0 ? "claude" : null), Sound = "msg.wav" }, 10);
    }

    // 30 dakikada bir (şehir ayarlıysa) anlık hava: yağmur/kar Sakura'nın arkasında yağar, sıcakta ter damlası.
    void WeatherFxCheck(DateTime now)
    {
        nextWeatherFx = now.AddMinutes(30);
        Task.Run(() => Weather.Current(cfg)).ContinueWith(t =>
        {
            if (t.Status != TaskStatus.RanToCompletion || t.Result == null) return;
            try { BeginInvoke((Action)(() => SetWeatherFx(Weather.Fx(t.Result[0], t.Result[1]), t.Result[1], true))); } catch { }
        });
    }

    void SetWeatherFx(string fx, int temp, bool comment)
    {
        bool changed = fx != weatherFx;
        weatherFx = fx;
        weatherTemp = temp;
        if (!changed || !comment || fx == "" || !Visible || ev != null || Quiet.ShouldHide(cfg)) return;
        string body = fx == "rain" ? "Dışarıda yağmur başladı~ Bugün içeride takılalım." : fx == "snow" ? "Kar yağıyor! Pencereden bakmak istiyorum~" : "Of, " + temp + "°C… Çok sıcak, su içmeyi unutma!";
        ShowEvent(new Event { Mode = "poke", Title = cfg.City, Body = body, Emote = fx == "hot" ? "utangac" : "saskin", Prefix = "idle_", Click = null, Sound = "" }, 6);
    }

    // Ulusal bayramlarda Türk bayrağı beresi: yeni çizimli görünümdeyse o gün yeni-bere'ye geçer, ertesi gün geri döner.
    static readonly string[] FlagDays = { "23.04", "19.05", "30.08", "29.10" };
    void HolidayHat(DateTime now)
    {
        bool day = FlagDays.Contains(now.ToString("dd.MM"));
        string look = cfg.Look ?? "";
        if (day && cfg.HatFrom == "" && (look == "yeni" || look.StartsWith("yeni-")) && look != "yeni-bere"
            && Directory.Exists(Path.Combine(Config.Dir, "frames", "yeni-bere")))
        {
            Config.Patch(c => { c.HatFrom = look; c.Look = "yeni-bere"; });
            ReloadSettings();
        }
        else if (!day && cfg.HatFrom != "")
        {
            string back = cfg.HatFrom;
            Config.Patch(c => { if (c.Look == "yeni-bere") c.Look = back; c.HatFrom = ""; });
            ReloadSettings();
        }
    }

    // Özel günler (günde bir kez her biri): bayramlar, doğum günü, Cuma akşamı. Doğum gününü bir kez sorar.
    void SpecialDays(DateTime now)
    {
        HolidayHat(now);
        string today = now.ToString("yyyy-MM-dd"), dm = now.ToString("dd.MM");
        string done = cfg.LastSpecial.StartsWith(today) ? cfg.LastSpecial : today;
        string key = null, title = null, body = null;
        bool party = true;
        var hijri = new UmAlQuraCalendar();
        int hm = -1, hd = -1;
        try { hm = hijri.GetMonth(now); hd = hijri.GetDayOfMonth(now); } catch { }
        if (now.Hour < 8) return;
        if (cfg.Birthday == dm) { key = "dogumgunu"; title = "Doğum günün!"; body = "İyi ki doğdun! Bugün senin günün, her şey gönlünce olsun~"; }
        else if (dm == "01.01") { key = "yilbasi"; title = "Mutlu yıllar!"; body = "Yeni yılda da hep yanındayım~"; }
        else if (dm == "14.02") { key = "sevgililer"; title = "Sevgililer Günü"; body = "Sevgililer Günü kutlu olsun~ Bana da çikolata var mı?"; }
        else if (dm == "23.04") { key = "23nisan"; title = "23 Nisan"; body = "Ulusal Egemenlik ve Çocuk Bayramı kutlu olsun! Bugün biraz oynayalım~"; }
        else if (dm == "19.05") { key = "19mayis"; title = "19 Mayıs"; body = "Gençlik ve Spor Bayramı kutlu olsun!"; }
        else if (dm == "30.08") { key = "30agustos"; title = "30 Ağustos"; body = "Zafer Bayramı kutlu olsun!"; }
        else if (dm == "29.10") { key = "29ekim"; title = "29 Ekim"; body = "Cumhuriyet Bayramımız kutlu olsun!"; }
        else if (dm == "31.12") { key = "yilsonu"; title = "Yılın son günü"; body = "Bu yıl birlikte çok şey yaptık~ Yarın yeni bir yıl!"; }
        else if (hm == 10 && hd == 1) { key = "ramazan"; title = "Ramazan Bayramı"; body = "Bayramın mübarek olsun! Şekerleri bana da ayır~"; }
        else if (hm == 12 && hd == 10) { key = "kurban"; title = "Kurban Bayramı"; body = "Bayramın mübarek olsun! Sevdiklerinle güzel bir bayram geçir~"; }
        else if (now.DayOfWeek == DayOfWeek.Friday && now.Hour >= 17) { key = "cuma"; title = "Cuma akşamı"; body = "Hafta bitti sayılır! Hafta sonu ne yapıyoruz~?"; party = false; }
        if (key != null && !done.Split(' ').Contains(key))
        {
            string ls = done + " " + key;
            cfg.LastSpecial = ls;
            Config.Patch(c => c.LastSpecial = ls);
            if (party) { Confetti(7); if (key == "dogumgunu") AddLove(5, false); }
            Notify(new Event { Mode = "party", Title = title, Body = body, Emote = party ? "nese" : "mutlu", Prefix = "wave_", Click = null, Sound = party ? "done.wav" : "" }, 9);
            return;
        }
        if (cfg.Birthday == "" && !cfg.BirthdayAsked && love >= 50 && now.Hour >= 10 && now.Hour < 22 && rnd.Next(40) == 0)
        {
            cfg.BirthdayAsked = true;
            Config.Patch(c => c.BirthdayAsked = true);
            ShowEvent(new Event { Mode = "poke", Body = "Bu arada doğum günün ne zaman? Söylersen hiç unutmam~", Footer = "Sağ tık → Sohbet'te yazabilirsin", Emote = "utangac", Prefix = "idle_", Click = null, Sound = "" }, 9);
        }
    }

    // Sakura'ya sor: Ctrl+Shift+Boşluk → panodaki metinle küçük yardım penceresi.
    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        if (!RegisterHotKey(Handle, HotkeyId, 0x2 | 0x4 | 0x4000, 0x20)) Program.LogQuiet("Sakura'ya sor: Ctrl+Shift+Boşluk kısayolu alınamadı (başka bir uygulama kullanıyor olabilir)");
    }

    protected override void OnHandleDestroyed(EventArgs e)
    {
        UnregisterHotKey(Handle, HotkeyId);
        base.OnHandleDestroyed(e);
    }

    public void AskClipboard(string text)
    {
        if (text == null) try { if (Clipboard.ContainsText()) text = Clipboard.GetText(); } catch { }
        text = (text ?? "").Trim();
        if (text == "")
        {
            Notify(new Event { Mode = "poke", Body = "Önce bir metni kopyala (Ctrl+C), sonra Ctrl+Shift+Boşluk'a bas~", Emote = "dusunce", Prefix = "idle_", Click = null, Sound = "" }, 5);
            return;
        }
        AskForm.ShowFor(this, text.Length > 20000 ? text.Substring(0, 20000) : text);
    }

    // Sakura'ya sor penceresi çalışırken düşünceli yüz ve düşünce balonu.
    public void SetThinking(bool on)
    {
        if (on) working["sor"] = DateTime.Now; else working.Remove("sor");
        Invalidate();
    }

    // Yerel tepkiyi hemen gösterir; yapay zekâ yorumları açıksa gelen kişisel cümleyi balona yazar.
    void AiRewrite(Event e, string what)
    {
        if (!cfg.AiComments || !Brain.Available(cfg)) return;
        Task.Run(() => Brain.Comment(cfg, what)).ContinueWith(t =>
        {
            if (t.Status != TaskStatus.RanToCompletion || string.IsNullOrEmpty(t.Result)) return;
            try { BeginInvoke((Action)(() => { if (ev == e) { e.Body = t.Result; ShowEvent(e, 6); } })); } catch { }
        });
    }

    void ScreenChecks(DateTime now)
    {
        string proc, title;
        Screen2.Foreground(out proc, out title);
        string video = Screen2.YouTubeVideo(proc, title);
        ytMusic = video != null && Screen2.IsMusic(video);
        // Video adı 3 saniye aynı kalınca (sekme gezinirken titreşmesin) bir kez tepki ver.
        if (video != seenVideo) { seenVideo = video; seenVideoAt = now; }
        if (video != null && video != lastVideo && (now - seenVideoAt).TotalSeconds >= 3 && (now - lastVideoReact).TotalSeconds >= 15 && ev == null)
        {
            lastVideo = video;
            lastVideoReact = now;
            var r = Screen2.VideoReaction(video);
            var vev = new Event { Mode = "screen", Title = "YouTube", Body = r[0], Emote = r[1], Prefix = "idle_", Click = null, Sound = "" };
            ShowEvent(vev, 5);
            AiRewrite(vev, "Kullanıcı şu an YouTube'da şu videoyu izliyor: “" + video + "”.");
        }
        if (proc != lastFgProcess)
        {
            lastFgProcess = proc;
            var a = Screen2.AppReaction(proc);
            DateTime t;
            if (a != null && ev == null && (!appReacted.TryGetValue(proc, out t) || (now - t).TotalHours >= 2))
            {
                appReacted[proc] = now;
                ShowEvent(new Event { Mode = "screen", Body = a[0], Emote = a[1], Prefix = "idle_", Click = null, Sound = "" }, 4);
            }
        }
    }

    void SystemChecks(DateTime now)
    {
        // Şarj
        var ps = SystemInformation.PowerStatus;
        if ((ps.BatteryChargeStatus & BatteryChargeStatus.NoSystemBattery) == 0 && ps.BatteryChargeStatus != BatteryChargeStatus.Unknown)
        {
            bool plugged = ps.PowerLineStatus == PowerLineStatus.Online;
            int pct = (int)Math.Round(ps.BatteryLifePercent * 100);
            if (pluggedIn == false && plugged)
                Notify(new Event { Mode = "system", Title = "Şarj", Body = "Oh, şarj geldi! Teşekkürler~", Emote = "nese", Prefix = "idle_", Click = null, Sound = "done.wav" }, 5);
            if (plugged) batteryWarnedAt = 101;
            else foreach (int lvl in new[] { 20, 10, 5 })
                    if (pct <= lvl && batteryWarnedAt > lvl)
                    {
                        batteryWarnedAt = lvl;
                        Notify(new Event { Mode = "system", Title = "Şarj %" + pct, Body = lvl == 5 ? "Şarjım bitmek üzere, hemen tak!" : "Şarjım bitiyor, prize takar mısın?", Emote = "uzgun", Prefix = "idle_", Click = null, Sound = "ask.wav" }, 8);
                        break;
                    }
            pluggedIn = plugged;
        }

        // İnternet: 20 saniyede bir kısa ping; 3 başarısız denemede "koptu", ilk başarıda "geldi".
        if (ticks % 150 == 0)
            Task.Run(() =>
            {
                try { using (var ping = new System.Net.NetworkInformation.Ping()) return ping.Send("1.1.1.1", 1500).Status == System.Net.NetworkInformation.IPStatus.Success; }
                catch { return false; }
            }).ContinueWith(t => { try { BeginInvoke((Action)(() => OnPing(t.Result))); } catch { } });

        // İşlemci / bellek: ~1 dakika boyunca yüksek kalırsa (yarım saatte en çok bir kez) uyar.
        int cpu = SysInfo.Cpu(), ram = SysInfo.Ram();
        cpuHighCount = cpu >= 90 ? cpuHighCount + 1 : 0;
        ramHighCount = ram >= 92 ? ramHighCount + 1 : 0;
        if (cpuHighCount >= 30 && (now - lastCpuWarn).TotalMinutes >= 30)
        {
            lastCpuWarn = now;
            Notify(new Event { Mode = "system", Title = "İşlemci %" + cpu, Body = "Bilgisayar çok zorlanıyor, biraz yavaşlayabilir.", Emote = "saskin", Prefix = "idle_", Click = null, Sound = "ask.wav" }, 7);
        }
        if (ramHighCount >= 30 && (now - lastRamWarn).TotalMinutes >= 30)
        {
            lastRamWarn = now;
            Notify(new Event { Mode = "system", Title = "Bellek %" + ram, Body = "Bellek neredeyse doldu, birkaç sekmeyi kapatsak mı?", Emote = "saskin", Prefix = "idle_", Click = null, Sound = "ask.wav" }, 7);
        }
    }

    void OnPing(bool ok)
    {
        if (!cfg.SystemAlerts) return;
        if (ok)
        {
            if (online == false) Notify(new Event { Mode = "system", Title = "İnternet", Body = "İnternet geri geldi!", Emote = "mutlu", Prefix = "idle_", Click = null, Sound = "done.wav" }, 5);
            online = true; netFails = 0;
        }
        else if (++netFails >= 3 && online != false)
        {
            if (online == true) Notify(new Event { Mode = "system", Title = "İnternet", Body = "İnternet bağlantısı koptu…", Emote = "uzgun", Prefix = "idle_", Click = null, Sound = "ask.wav" }, 6);
            online = false;
        }
    }

    // İndirilenler klasöründe geçici dosya (.crdownload, .part, ...) son adına dönünce "indirme bitti".
    void StartDownloadWatch()
    {
        try
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
            if (!Directory.Exists(dir)) return;
            downloads = new FileSystemWatcher(dir) { IncludeSubdirectories = false, EnableRaisingEvents = true };
            string[] temp = { ".crdownload", ".part", ".tmp", ".download", ".partial", ".opdownload" };
            downloads.Renamed += (s, e) =>
            {
                string oldExt = Path.GetExtension(e.OldName).ToLowerInvariant(), newExt = Path.GetExtension(e.Name).ToLowerInvariant();
                if (!temp.Contains(oldExt) || temp.Contains(newExt)) return;
                try
                {
                    BeginInvoke((Action)(() =>
                    {
                        if (!cfg.SystemAlerts || cfg.SnoozeUntil > DateTime.Now) return;
                        Notify(new Event { Mode = "system", Title = "İndirme bitti", Body = e.Name, Emote = "nese", Prefix = "idle_", Click = "file:" + e.FullPath, Sound = "done.wav" }, 6);
                    }));
                }
                catch { }
            };
        }
        catch (Exception ex) { Program.LogError(ex); }
    }

    void OnTick(object s, EventArgs e)
    {
        var now = DateTime.Now;
        if (roamSet == null && !roamWarming && !shooting && ticks > 40 && ticks % 40 == 0) WarmRoam(); // çekimde işlemciyi kayda bırak
        if (dblPendingAt != DateTime.MinValue && (now - dblPendingAt).TotalSeconds >= 0.45)
        {
            dblPendingAt = DateTime.MinValue;
            if (clickTimes.Count(t => (now - t).TotalSeconds <= 1.2) <= 2) AppFocus.Open("claude"); // gıdıklama değilse
        }
        // mini: tam ekrana girip çıkınca ~0,7 sn içinde (her 5 tıkta bir) değişsin
        if (ticks % 5 == 2) { try { UpdateMini(now); } catch (Exception ex) { Program.LogError(ex); } }
        if (ticks++ % 15 == 0)
        {
            // Tam ekran oyun/video sırasında (ayara göre) gizlen, bitince geri gel.
            bool hide = Quiet.ShouldHide(cfg);
            if (hide != quietHidden)
            {
                string proc, title;
                Screen2.Foreground(out proc, out title);
                Program.LogQuiet((hide ? "gizlendi" : "geri geldi") + " durum=" + Quiet.State() + " tam_ekran=" + Quiet.ForegroundFullscreen() + " on_plan=" + proc);
                quietHidden = hide;
                if (hide && popup != null && !popup.IsDisposed) popup.Close();
            }
            if (hide && Visible) Hide();
            else if (!hide && !Visible && allowShow) Show();
            if (missed.Count > 0) pending = null; // dönüşte hepsi tek özette gösterilir
            if (!hide && !mini && pending != null)
            {
                var p = pending;
                pending = null;
                p.Phoned = true;
                if ((now - pendingAt).TotalMinutes < 15) Notify(p, (int)Math.Ceiling(cfg.Seconds + 2));
            }
            try { SlowChecks(now); } catch (Exception ex) { Program.LogError(ex); }
        }
        if (!Visible) return;
        if (mini) { MiniTick(now); return; }
        // Luna'nın sesi: gezinti/uçuş dalları aşağıda erken döndüğü için kontrol burada (fırlatılıp oturunca da konuşsun)
        if (ev != null && now >= voiceAt)
        {
            voiceAt = DateTime.MaxValue;
            if (Desk.IsSetUp) Program.LogQuiet("ses " + now.ToString("HH:mm:ss.fff") + "|" + ev.Emote + "|" + ev.Body);
            if (ev.Mode != "jarvis") Voice.Say(cfg, ev.Body, ev.Emote, VoiceMax); // asistanın sesini Python çalar
        }
        if (roam == 0 && sceneNext != null && now >= sceneAt) { var a = sceneNext; sceneNext = null; a(); }
        if (motion != null && roam == 0)
        {
            StepMotion(now);
            if ((now - frameAt).TotalMilliseconds >= 135) { frameAt = now; frame = (frame + 1) % current.Count; }
            return;
        }
        if (roam != 0)
        {
            if (ev != null && ev.Mode != "poke") EndRoam();
            else
            {
                if (ev != null && now >= evUntil) { ev = null; SetSitMood(null); }
                if (now >= talkUntil && current != null) { if (current == standTalk) current = standIdle; else if (current == sitTalk) current = sitIdle; }
                if (motion != null) StepMotion(now);
                else if (!dragging) RoamTick(now);
                // 140 ms'de bir kare (70 ms'lik tıkta 2 tık): 8 karelik döngü ~1,1 sn
                if ((now - frameAt).TotalMilliseconds >= 135) { frameAt = now; frame = (frame + 1) % current.Count; }
                Invalidate();
                return;
            }
        }
        if (ev != null && now >= evUntil) BackToIdle();
        if (ev != null)
        {
            // selam bitince konuşmaya, konuşma bitince ifadenin bekleme karelerine geç
            if (evPhase == 0 && frame + 1 >= current.Count)
            {
                evPhase = 1;
                current = evTalk ?? evIdle;
                talkUntil = now.AddSeconds(evTalkSec);
                frame = -1;
                voiceAt = now;
            }
            else if (evPhase == 1 && now >= talkUntil && current != evIdle)
            {
                evPhase = 2;
                current = evIdle;
                frame = -1;
            }
        }
        // Uyuklama: 10 dk dokunulmazsa uykulu yüz + Zzz; fare/klavye uyandırır.
        if (sleeping)
        {
            if ((Activity.IdleSeconds() < 1.5 && (now - sleptAt).TotalSeconds > 4) || working.Count > 0)
            {
                nextRoam = now.AddMinutes(rnd.Next(2, 5));
                ShowEvent(new Event { Mode = "poke", Body = WakeLines[rnd.Next(WakeLines.Length)], Emote = "uykulu", Prefix = "idle_", Click = null, Sound = "" }, 4);
            }
            else { frame = (frame + 1) % current.Count; Invalidate(); return; }
        }
        else if (ev == null && current == idle && working.Count == 0 && !dragging && !playing && ticks % 15 == 1 && Activity.IdleSeconds() >= 600)
        {
            FallAsleep();
            return;
        }
        // İmlece bakma: fare yanına gelince kısa bir bakış; üstünde 6 sn durursa yorum.
        var sr = new Rectangle(Left + Width - spriteW, Top + Height - spriteH, spriteW, spriteH);
        sr.Inflate(70, 70);
        bool near = sr.Contains(Cursor.Position);
        if (near && !cursorNear && ev == null && current == idle && !dragging && (now - lastGlance).TotalSeconds >= 25)
        {
            lastGlance = now;
            bool right = Cursor.Position.X > Left + Width - spriteW / 2;
            if (HasLook()) current = EmoteFrames(right ? "bak_sag" : "bak_sol"); // gözleriyle imlecin tarafına bakar
            else
            {
                string[] looks = { "utangac", "saskin", "goz_kirp" };
                current = EmoteFrames(looks[rnd.Next(looks.Length)]);
            }
            moodUntil = now.AddSeconds(2.5);
            frame = 0;
            PlayAnim("bakis", right); // klip sola eğilir; imleç sağdaysa ayna
        }
        cursorNear = near;
        // Arada bir kendiliğinden sağa ya da sola bakar (çizilmiş bakış kareleri varsa)
        if (ev == null && current == idle && !dragging && now >= nextLook)
        {
            nextLook = now.AddSeconds(rnd.Next(30, 80));
            if (HasLook())
            {
                bool right = rnd.Next(2) == 0;
                current = EmoteFrames(right ? "bak_sag" : "bak_sol");
                moodUntil = now.AddSeconds(1.5 + rnd.NextDouble());
                frame = 0;
            }
        }
        if (hovering && !dragging && ev == null && (now - hoverSince).TotalSeconds >= 6 && (now - lastHoverTalk).TotalMinutes >= 3)
        {
            lastHoverTalk = now;
            ShowEvent(new Event { Mode = "poke", Body = HoverLines[rnd.Next(HoverLines.Length)], Emote = "utangac", Prefix = "idle_", Click = null, Sound = "" }, 4);
        }
        // Claude çalışırken düşünceli yüz (çizimi varsa); iş bitince normale döner
        bool think = working.Count > 0 && ev == null && !shooting && HasFrames(cfg.Look, "idle_", "dusunce");
        if (think && current == idle) { current = thinkFrames ?? (thinkFrames = LoadFrames("idle_", "dusunce")); frame = 0; }
        else if (!think && ev == null && thinkFrames != null && current == thinkFrames) { current = idle; frame = 0; }
        if (ev == null && current == idle && working.Count == 0 && !hovering && !dragging && now >= nextRoam && CanRoam())
        {
            StartRoam();
            Invalidate();
            return;
        }
        if (ev == null && current != idle && current != thinkFrames && now >= moodUntil) BackToIdle();
        if (cfg.AnimOn && Visible && ev == null && roam == 0 && !sleeping && !dragging && shot == null && motion == null) IdleLife(now);
        if (ev == null && current == idle && now >= nextMood)
        {
            // Ara sıra kendi kendine bir ifade takınır; sevgiye göre.
            string[] pool = love >= 80 ? new[] { "sevgi", "nese", "mutlu", "goz_kirp" } : love <= 25 ? new[] { "uzgun", "utangac" } : Moods;
            string mood = pool[rnd.Next(pool.Length)];
            current = Shrink(new Sprites(cfg.Look, "idle_", mood).Render(cfg.Colors));
            PlayAnim("ifade:" + mood);
            moodUntil = now.AddSeconds(4);
            nextMood = now.AddSeconds(rnd.Next(60, 150));
            frame = 0;
        }
        frame = (frame + 1) % current.Count;
        Invalidate();
    }

    // Yağmur damlaları / kar taneleri: Sakura'nın arkasında (önce çizilir), sprite alanında süzülür.
    void DrawWeather(Graphics g, int sx, int sy, float k)
    {
        var st = g.Save();
        g.SmoothingMode = SmoothingMode.AntiAlias;
        // Sakura'nın arkası ve solundaki boşluk (balon alanı): yalnız sprite alanında neredeyse görünmüyordu
        int left = (int)(80 * k), w = spriteW + left, h = spriteH;
        sx -= left;
        if (weatherFx == "rain")
            using (var pen = new Pen(Color.FromArgb(200, 150, 190, 255), Math.Max(1.4f, 1.8f * k)) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                for (int i = 0; i < 40; i++)
                {
                    int sp = 18 + (i * 7) % 11;
                    float x = sx + (i * 53 + 17) % w, y = sy - 20 + (ticks * sp + i * 97) % (h + 30);
                    g.DrawLine(pen, x, y, x - 4 * k, y + 15 * k);
                }
        else
            using (var flake = new SolidBrush(Color.FromArgb(220, 255, 255, 255)))
            using (var rim = new SolidBrush(Color.FromArgb(90, 120, 140, 180)))
                for (int i = 0; i < 34; i++)
                {
                    int sp = 3 + (i * 5) % 4;
                    float r = (2 + (i % 3)) * k;
                    float x = sx + (i * 61 + 11) % w + (float)(Math.Sin(ticks * 0.15 + i) * 6 * k), y = sy - 10 + (ticks * sp + i * 83) % (h + 20);
                    g.FillEllipse(rim, x - r - 0.8f, y - r - 0.8f, 2 * r + 1.6f, 2 * r + 1.6f);
                    g.FillEllipse(flake, x - r, y - r, 2 * r, 2 * r);
                }
        g.Restore(st);
    }

    // Sıcakta şakağında ter damlası (hafifçe kayar).
    void DrawSweat(Graphics g, int sx, int sy, float k)
    {
        var st = g.Save();
        g.SmoothingMode = SmoothingMode.AntiAlias;
        float x = sx + spriteW * 0.64f, y = sy + spriteH * 0.27f + (ticks % 14) * 0.6f * k, r = 5 * k;
        using (var p = new GraphicsPath())
        {
            p.AddBezier(x, y - 2.2f * r, x + 0.2f * r, y - 1.2f * r, x + r, y - 0.6f * r, x + r, y);
            p.AddArc(x - r, y - r, 2 * r, 2 * r, 0, 180);
            p.AddBezier(x - r, y, x - r, y - 0.6f * r, x - 0.2f * r, y - 1.2f * r, x, y - 2.2f * r);
            using (var pen = new Pen(Color.FromArgb(200, 60, 110, 190), 1.4f * k)) g.DrawPath(pen, p);
            using (var b = new SolidBrush(Color.FromArgb(220, 170, 215, 255))) g.FillPath(b, p);
        }
        using (var hl = new SolidBrush(Color.FromArgb(230, 255, 255, 255))) g.FillEllipse(hl, x - 0.5f * r, y - 0.6f * r, 0.45f * r, 0.45f * r);
        g.Restore(st);
    }

    // Konfeti: renkli kâğıtlar sprite alanının tepesinden dönerek düşer.
    void DrawConfetti(Graphics g, int sx, int sy, float k)
    {
        var st = g.Save();
        g.SmoothingMode = SmoothingMode.AntiAlias;
        double t = (DateTime.Now - confettiFrom).TotalSeconds;
        Color[] cols = { Color.FromArgb(255, 105, 160), Color.FromArgb(255, 210, 70), Color.FromArgb(110, 200, 255), Color.FromArgb(150, 230, 140), Color.FromArgb(190, 140, 255), Color.White };
        for (int i = 0; i < 46; i++)
        {
            double sp = 110 + (i * 37) % 90, delay = (i * 0.137) % 1.6;
            double tt = t - delay;
            if (tt < 0) continue;
            float x = sx + (i * 47 + 13) % spriteW + (float)(Math.Sin(tt * 3 + i) * 10 * k), y = sy - 12 * k + (float)(tt * sp * k);
            if (y > sy + spriteH) continue;
            int a = (int)(255 * Math.Max(0, Math.Min(1, (confettiUntil - DateTime.Now).TotalSeconds / 1.2)));
            using (var b = new SolidBrush(Color.FromArgb(a, cols[i % cols.Length])))
            {
                var gs = g.Save();
                g.TranslateTransform(x, y);
                g.RotateTransform((float)(tt * (200 + i * 13) % 360));
                g.FillRectangle(b, -2.5f * k, -4.5f * k, 5 * k, 9 * k * (float)Math.Abs(Math.Cos(tt * 5 + i)) + 1);
                g.Restore(gs);
            }
        }
        g.Restore(st);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        Pixelated(g);
        int sx = Width - spriteW - flightPad, sy = Height - spriteH - flightPad;
        float k = spriteW / 192f;
        int bob = !cfg.AnimOn && playing && ev == null && roam == 0 && (ticks / 2) % 2 == 1 ? (int)Math.Max(1, 2 * k) : 0;
        var cur = current[Math.Max(0, frame) % current.Count];
        if (!mini && (weatherFx == "rain" || weatherFx == "snow")) DrawWeather(g, sx, sy, k);
        var pose = drawnPose = CurrentPose();
        drawnAt = DateTime.Now;
        var dest = roam != 0 ? new RectangleF(sx + (spriteW - cur.Width) / 2, Height - flightPad - cur.Height, cur.Width, cur.Height) : new RectangleF(sx, sy - bob, spriteW, spriteH);
        Anim.Draw(g, cur, dest, pose, roam == 0 && !mini && Math.Abs(pose.Rot) < 8, Anim.Smooth(cfg.Look)); // takla atarken kesik alt kenar uzatılmaz
        var head = Anim.HeadTop(dest, roam == 0 && !mini, pose);
        var stc = StateClip();
        if (stc != null && stc.Fx != null && (shot == null || shot.Fx == null)) Anim.DrawFx(g, stc.Fx, (DateTime.Now - animEpoch).TotalSeconds, stc.FxDur, head, dest.Height / 256f, true);
        if (shot != null && shot.Fx != null) Anim.DrawFx(g, shot.Fx, (DateTime.Now - shotAt).TotalSeconds - shot.FxAt, shot.FxDur, head, dest.Height / 256f);
        using (var ink = new SolidBrush(Bubble.Ink))
        using (var white = new SolidBrush(Color.White))
        {
            if (working.Count > 0 && ev == null && !shooting && !mini)
            {
                // Düşünce balonu: kafanın sol üstünde, noktalar sırayla belirir.
                int cx = sx + (int)(10 * k), cy = sy + (int)(14 * k), cw = (int)(46 * k), ch = (int)(22 * k);
                g.FillRectangle(ink, cx + 2, cy, cw - 4, ch);
                g.FillRectangle(ink, cx, cy + 2, cw, ch - 4);
                g.FillRectangle(white, cx + 2, cy + 2, cw - 4, ch - 4);
                for (int i = 0; i < 2; i++)
                {
                    int r = (int)((5 - 2 * i) * k) + 2, px = cx + cw - (int)(6 * k) + i * (int)(8 * k), py = cy + ch + (int)(3 * k) + i * (int)(8 * k);
                    g.FillRectangle(ink, px, py, r, r);
                    g.FillRectangle(white, px + 1, py + 1, r - 2, r - 2);
                }
                int dots = (ticks / 4) % 4, ds = Math.Max(2, (int)(4 * k));
                for (int i = 0; i < dots; i++) g.FillRectangle(ink, cx + (int)(10 * k) + i * (int)(11 * k), cy + ch / 2 - ds / 2, ds, ds);
                if (working.Count > 1)
                    using (var f = new Font("Segoe UI", 10f, FontStyle.Bold, GraphicsUnit.Pixel))
                        g.DrawString(working.Count.ToString(), f, ink, cx + cw - (int)(9 * k), cy - (int)(2 * k));
            }
            if (playing && ev == null && !mini && !(cfg.AnimOn && Anim.ForTrigger("muzik") != null && Anim.ForTrigger("muzik").Fx != null))
            {
                // Müzik notası: başın sağında yukarı süzülür.
                int nx = sx + (int)(160 * k), ny = sy + (int)((40 - (ticks % 20)) * k), u = Math.Max(1, (int)(2 * k));
                using (var note = new SolidBrush(Color.FromArgb(150, 110, 240)))
                {
                    var strokes = new[] { new Rectangle(nx + 3 * u, ny, u, 7 * u), new Rectangle(nx, ny + 6 * u, 4 * u, 3 * u), new Rectangle(nx + 3 * u, ny, 3 * u, u) };
                    foreach (var r in strokes) g.FillRectangle(ink, r.X - 1, r.Y - 1, r.Width + 2, r.Height + 2);
                    foreach (var r in strokes) g.FillRectangle(note, r);
                }
            }
            if ((hovering || DateTime.Now < loveShowUntil) && !Desk.IsSetUp) // çekim masaüstünde sevgi barı görünmez
            {
                float z = cfg.PetSmall ? 0.7f : 1f, bw = 150 * z;
                // Sakura ekranın kenarından taşıyorsa bar ekranın içinde kalsın
                var wa = Screen.FromControl(this).WorkingArea;
                float bx = Math.Max(wa.Left - Left + 4 * z, Math.Min(sx + spriteW - bw - 6 * z, wa.Right - Left - bw - 6 * z));
                LoveBar.Draw(g, bx, Math.Max(wa.Top - Top + 4 * z, sy + 4 * z), z, love, LevelNames[Level()]);
            }
        }
        if (weatherFx == "hot" && roam == 0 && !mini && !sleeping) DrawSweat(g, sx, sy - bob, k);
        if (DateTime.Now < confettiUntil) DrawConfetti(g, sx, sy, k);
        if (sleeping)
            for (int i = 0; i < 3; i++)
            {
                // üç "z" uykulu çizimin kendi küçük z'lerinden (sol üst) sırayla yükselip kaybolur
                double p = ((ticks + i * 7) % 21) / 21.0;
                float zx = sx + spriteW * 0.14f - (float)(i * 5 * k + p * 12 * k), zy = sy + spriteH * 0.20f - (float)(p * 46 * k);
                int a = (int)(255 * (1 - p));
                using (var ink2 = new SolidBrush(Color.FromArgb(a, Bubble.Ink)))
                using (var zb = new SolidBrush(Color.FromArgb(a, 170, 150, 240)))
                using (var zf = new Font("Segoe UI", (10 + i * 3) * k, FontStyle.Bold, GraphicsUnit.Pixel))
                {
                    for (int ox = -1; ox <= 1; ox++)
                        for (int oy = -1; oy <= 1; oy++)
                            if (ox != 0 || oy != 0) g.DrawString("z", zf, ink2, zx + ox, zy + oy);
                    g.DrawString("z", zf, zb, zx, zy);
                }
            }
        if (ev != null && talkScene)
        {
            int bx = bubbleArea.Width > spriteW ? sx + spriteW - bubbleArea.Width : sx + (spriteW - bubbleArea.Width) / 2;
            Bubble.DrawFilm(g, new Rectangle(bx, Math.Max(0, sy - bubbleArea.Height), bubbleArea.Width, bubbleArea.Height), ev);
        }
        else if (ev != null)
            Bubble.Draw(g, new Rectangle(sx - Gap - bubbleArea.Width, Math.Max(0, sy + spriteH / 6 - bubbleArea.Height / 3), bubbleArea.Width, bubbleArea.Height), ev);
    }
}

// WhatsApp/Telegram/Discord mesajları ve Outlook toplantı hatırlatmaları: Windows'un bildirim kaydını (wpndatabase.db)
// salt okunur yoklar. Windows'un kendi winsqlite3.dll'i kullanılır (Python gerekmez). Mesaj içeriği okunmaz;
// yalnızca yeni bildirimin varış zamanına bakılır (WhatsApp aynı sohbetin bildirimini yenilediği için sıra numarası değil).
class MessageWatch : IDisposable
{
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_open_v2")] static extern int Open(byte[] file, out IntPtr db, int flags, IntPtr vfs);
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_prepare_v2")] static extern int Prepare(IntPtr db, byte[] sql, int n, out IntPtr stmt, IntPtr tail);
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_step")] static extern int Step(IntPtr stmt);
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_column_int64")] static extern long ColumnInt64(IntPtr stmt, int col);
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_finalize")] static extern int Finalize(IntPtr stmt);
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_close")] static extern int CloseDb(IntPtr db);
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_busy_timeout")] static extern int BusyTimeout(IntPtr db, int ms);

    // uygulama, NotificationHandler.PrimaryId kalıbı, ek koşul
    static readonly string[,] Apps = {
        { "whatsapp", "%WhatsApp%", "" },
        { "telegram", "%Telegram%", "" },
        { "discord", "%Discord%", "" },
        { "outlook", "%Outlook%", " AND n.Payload LIKE '%scenario=\"reminder\"%'" },
    };
    static readonly string Db = Environment.ExpandEnvironmentVariables(@"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db");

    readonly System.Threading.Timer timer;
    readonly Action<string> onNew;
    Dictionary<string, long> last;
    DateTime lastPopup = DateTime.MinValue;
    int busy;

    public MessageWatch(Action<string> onNew)
    {
        this.onNew = onNew;
        timer = new System.Threading.Timer(Tick, null, 2000, 2000);
    }

    static byte[] U(string s) { return Encoding.UTF8.GetBytes(s + "\0"); }

    internal static Dictionary<string, long> Read()
    {
        IntPtr db;
        if (Open(U("file:///" + Db.Replace('\\', '/') + "?mode=ro"), out db, 0x01 | 0x40, IntPtr.Zero) != 0)
        {
            if (db != IntPtr.Zero) CloseDb(db);
            return null;
        }
        try
        {
            BusyTimeout(db, 1000);
            var r = new Dictionary<string, long>();
            for (int i = 0; i < Apps.GetLength(0); i++)
            {
                string sql = "SELECT MAX(n.ArrivalTime) FROM Notification n JOIN NotificationHandler h ON n.HandlerId = h.RecordId " +
                             "WHERE n.Type = 'toast' AND h.PrimaryId LIKE '" + Apps[i, 1] + "'" + Apps[i, 2];
                IntPtr st;
                if (Prepare(db, U(sql), -1, out st, IntPtr.Zero) != 0) return null;
                try { r[Apps[i, 0]] = Step(st) == 100 ? ColumnInt64(st, 0) : 0; }
                finally { Finalize(st); }
            }
            return r;
        }
        finally { CloseDb(db); }
    }

    void Tick(object state)
    {
        if (Interlocked.Exchange(ref busy, 1) == 1) return;
        try
        {
            var cur = Read();
            if (cur == null) return;
            if (last == null) { last = cur; return; } // açılışta eski bildirimler için çıkma
            var fresh = cur.Keys.Where(k => cur[k] > last[k]).ToList();
            last = cur;
            if (fresh.Count > 0 && (DateTime.Now - lastPopup).TotalSeconds >= 6)
            {
                lastPopup = DateTime.Now;
                onNew(fresh[0]);
            }
        }
        catch (Exception ex) { Program.LogError(ex); }
        finally { busy = 0; }
    }

    public void Dispose() { timer.Dispose(); }
}

// Günlük istatistik: her bildirim stats.csv'ye bir satır yazar (zaman;tür;ayrıntı;dakika).
static class Stats
{
    static string FilePath { get { return Path.Combine(Config.Dir, "stats.csv"); } }

    public class Day { public DateTime Date; public int Done, Errors, Msgs, Breaks; public double Minutes, Longest; }

    public static void Log(string kind, string detail, double minutes)
    {
        try
        {
            File.AppendAllText(FilePath, string.Format(CultureInfo.InvariantCulture, "{0:s};{1};{2};{3:0.0}{4}",
                DateTime.Now, kind, (detail ?? "").Replace(";", ","), minutes, Environment.NewLine));
        }
        catch { }
    }

    public static List<Day> Days(int n)
    {
        var days = Enumerable.Range(0, n).Select(i => new Day { Date = DateTime.Today.AddDays(i - n + 1) }).ToList();
        if (!File.Exists(FilePath)) return days;
        foreach (var line in File.ReadAllLines(FilePath))
        {
            var p = line.Split(';');
            DateTime t;
            if (p.Length < 4 || !DateTime.TryParse(p[0], CultureInfo.InvariantCulture, DateTimeStyles.None, out t)) continue;
            var d = days.FirstOrDefault(x => x.Date == t.Date);
            if (d == null) continue;
            double m;
            double.TryParse(p[3], NumberStyles.Float, CultureInfo.InvariantCulture, out m);
            if (p[1] == "done") { d.Done++; d.Minutes += m; d.Longest = Math.Max(d.Longest, m); }
            else if (p[1] == "error") d.Errors++;
            else if (p[1] == "msg") d.Msgs++;
            else if (p[1] == "break") d.Breaks++;
        }
        return days;
    }

    public static Day Today() { return Days(1)[0]; }

    public static string Dur(double minutes)
    {
        int m = (int)Math.Round(minutes);
        return m < 60 ? m + " dk" : (m / 60) + " sa " + (m % 60) + " dk";
    }

    public static Event TodaySummary(bool onDemand)
    {
        var d = Today();
        return new Event
        {
            Mode = "summary",
            Title = onDemand ? "Bugünün özeti" : "Günün özeti",
            Body = d.Done == 0 ? "Bugün henüz birlikte bir iş bitirmedik." : string.Format("Bugün {0} iş bitirdik, toplam {1}.", d.Done, Dur(d.Minutes)),
            Footer = string.Format("En uzunu {0} · {1} mola · {2} mesaj", Dur(d.Longest), d.Breaks, d.Msgs),
            Emote = d.Done >= 5 ? "gurur" : "mutlu",
            Click = null,
        };
    }
}

// Haftalık istatistik penceresi: son 7 günün iş sayısı (çubuk), toplam süre, mola ve mesajlar.
class StatsForm : Form
{
    readonly List<Stats.Day> days = Stats.Days(7);

    public StatsForm()
    {
        Text = "Sakura — Haftalık istatistik";
        Font = new Font("Segoe UI", 9.5f);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(32, 30, 40);
        ForeColor = Color.FromArgb(235, 232, 240);
        ClientSize = new Size(600, 330);
        DoubleBuffered = true;
        var exeIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if (exeIcon != null) Icon = exeIcon;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        var tr = new CultureInfo("tr-TR");
        int max = Math.Max(1, days.Max(d => d.Done)), y = 20;
        using (var bar = new SolidBrush(Color.FromArgb(214, 70, 120)))
        using (var dim = new SolidBrush(Color.FromArgb(170, 165, 185)))
        using (var fg = new SolidBrush(ForeColor))
        using (var bold = new Font(Font, FontStyle.Bold))
        {
            g.DrawString("Son 7 gün", bold, fg, 16, y);
            y += 30;
            foreach (var d in days)
            {
                g.DrawString(d.Date.ToString("ddd dd.MM", tr), d.Date == DateTime.Today ? bold : Font, fg, 16, y);
                int w = (int)(220.0 * d.Done / max);
                if (w > 0) g.FillRectangle(bar, 110, y + 3, w, 14);
                g.DrawString(d.Done + " iş", fg == null ? Font : bold, fg, 110 + Math.Max(w, 0) + 6, y);
                g.DrawString(string.Format("{0} · {1} mola · {2} mesaj", Stats.Dur(d.Minutes), d.Breaks, d.Msgs), Font, dim, 400, y);
                y += 30;
            }
            var all = days;
            g.DrawString(string.Format("Toplam: {0} iş, {1}, {2} mola, {3} mesaj", all.Sum(d => d.Done), Stats.Dur(all.Sum(d => d.Minutes)), all.Sum(d => d.Breaks), all.Sum(d => d.Msgs)), bold, fg, 16, y + 6);
        }
    }
}

// Kurulum ve kaldırma: Windows "Uygulamalar" listesine kayıt, Başlat menüsü ve açılış kısayolları.
static class Installer
{
    const string Key = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Sakura";
    static string Programs { get { return Environment.GetFolderPath(Environment.SpecialFolder.Programs); } }
    static string StartupDir { get { return Environment.GetFolderPath(Environment.SpecialFolder.Startup); } }

    public static void Shortcut(string path, string args, string desc)
    {
        try
        {
            var shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
            object lnk = shell.GetType().InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] { path });
            var t = lnk.GetType();
            t.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, lnk, new object[] { Application.ExecutablePath });
            t.InvokeMember("Arguments", System.Reflection.BindingFlags.SetProperty, null, lnk, new object[] { args });
            t.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, lnk, new object[] { Config.Dir });
            t.InvokeMember("Description", System.Reflection.BindingFlags.SetProperty, null, lnk, new object[] { desc });
            t.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, lnk, null);
        }
        catch (Exception ex) { Program.LogError(ex); }
    }

    static void Delete(string path) { try { if (File.Exists(path)) File.Delete(path); } catch { } }

    public static void Install()
    {
        long kb = new DirectoryInfo(Config.Dir).GetFiles("*", SearchOption.AllDirectories).Sum(f => f.Length) / 1024;
        using (var k = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(Key))
        {
            k.SetValue("DisplayName", "Sakura");
            k.SetValue("DisplayIcon", Application.ExecutablePath);
            k.SetValue("DisplayVersion", "1.0");
            k.SetValue("Publisher", "Sakura");
            k.SetValue("InstallLocation", Config.Dir);
            k.SetValue("UninstallString", "\"" + Application.ExecutablePath + "\" uninstall");
            k.SetValue("EstimatedSize", (int)kb, Microsoft.Win32.RegistryValueKind.DWord);
            k.SetValue("NoModify", 1, Microsoft.Win32.RegistryValueKind.DWord);
            k.SetValue("NoRepair", 1, Microsoft.Win32.RegistryValueKind.DWord);
        }
        Shortcut(Path.Combine(Programs, "Sakura.lnk"), "", "Sakura masaüstü arkadaşı");
        Shortcut(Path.Combine(Programs, "Sakura Görünüm.lnk"), "menu", "Sakura görünüm ayarları");
        Startup.Add();
        // Eski sürümün parçaları: ayrı arkadaş kısayolu ve Python mesaj izleyicisi.
        Delete(Path.Combine(StartupDir, "Sakura arkadaş.lnk"));
        Delete(Path.Combine(StartupDir, "Sakura WhatsApp izleyici.lnk"));
        try
        {
            using (var q = new System.Management.ManagementObjectSearcher("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'pythonw.exe'"))
                foreach (System.Management.ManagementObject p in q.Get())
                    if ((p["CommandLine"] ?? "").ToString().Contains("whatsapp_watch")) p.InvokeMethod("Terminate", new object[] { 0 });
        }
        catch { }
    }

    public static void Uninstall()
    {
        if (MessageBox.Show("Sakura kaldırılsın mı?\n\nClaude ayarlarındaki Sakura bağlantıları, kısayollar ve Sakura klasörü (" + Config.Dir + ") silinecek.",
                "Sakura'yı kaldır", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        RemoveClaudeHooks();
        PetForm.CloseRunning();
        foreach (var p in Process.GetProcessesByName("Sakura")) if (p.Id != Process.GetCurrentProcess().Id) try { p.Kill(); } catch { }
        Delete(Path.Combine(Programs, "Sakura.lnk"));
        Delete(Path.Combine(Programs, "Sakura Görünüm.lnk"));
        Startup.Remove();
        try { Microsoft.Win32.Registry.CurrentUser.DeleteSubKeyTree(Key, false); } catch { }
        MessageBox.Show("Sakura kaldırıldı. Görüşmek üzere!", "Sakura", MessageBoxButtons.OK, MessageBoxIcon.Information);
        // Program kapandıktan sonra klasörü sil.
        Process.Start(new ProcessStartInfo("cmd.exe", "/c timeout /t 3 /nobreak >nul & rmdir /s /q \"" + Config.Dir + "\"")
            { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden });
    }

    // ~/.claude/settings.json içinden yalnızca Sakura'yı çağıran hook'ları siler (önce yedek alır).
    static void RemoveClaudeHooks()
    {
        try
        {
            string sp = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude", "settings.json");
            if (!File.Exists(sp)) return;
            File.Copy(sp, sp + ".sakura-yedek", true);
            var js = new JavaScriptSerializer();
            var root = js.Deserialize<Dictionary<string, object>>(File.ReadAllText(sp));
            var hooks = root.ContainsKey("hooks") ? root["hooks"] as Dictionary<string, object> : null;
            if (hooks == null) return;
            foreach (var name in hooks.Keys.ToList())
            {
                var keep = new System.Collections.ArrayList();
                foreach (var grpObj in (System.Collections.ArrayList)hooks[name])
                {
                    var grp = (Dictionary<string, object>)grpObj;
                    var hk = new System.Collections.ArrayList();
                    foreach (var hObj in (System.Collections.ArrayList)grp["hooks"])
                    {
                        var h = (Dictionary<string, object>)hObj;
                        if (!(h.ContainsKey("command") && h["command"].ToString().IndexOf("sakura", StringComparison.OrdinalIgnoreCase) >= 0)) hk.Add(h);
                    }
                    if (hk.Count > 0) { grp["hooks"] = hk; keep.Add(grp); }
                }
                if (keep.Count > 0) hooks[name] = keep; else hooks.Remove(name);
            }
            if (hooks.Count == 0) root.Remove("hooks");
            File.WriteAllText(sp, js.Serialize(root));
        }
        catch (Exception ex) { Program.LogError(ex); }
    }
}

// Claude API anahtarı: Windows DPAPI ile yalnızca bu kullanıcı hesabının çözebileceği şekilde şifrelenip saklanır.
// Anahtar yoksa ANTHROPIC_API_KEY ortam değişkenine bakılır.
static class ApiKey
{
    static string FilePath { get { return Path.Combine(Config.Dir, "apikey.dat"); } }

    public static string Get()
    {
        try
        {
            if (File.Exists(FilePath))
                return Encoding.UTF8.GetString(System.Security.Cryptography.ProtectedData.Unprotect(
                    File.ReadAllBytes(FilePath), null, System.Security.Cryptography.DataProtectionScope.CurrentUser));
        }
        catch { }
        return Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? "";
    }

    public static bool Has() { return Get() != ""; }

    public static void Set(string key)
    {
        if (string.IsNullOrWhiteSpace(key)) { try { File.Delete(FilePath); } catch { } return; }
        File.WriteAllBytes(FilePath, System.Security.Cryptography.ProtectedData.Protect(
            Encoding.UTF8.GetBytes(key.Trim()), null, System.Security.Cryptography.DataProtectionScope.CurrentUser));
    }
}

// Sakura'nın "beyni": kısa, kişilikli Türkçe cevaplar üretir. İki yol:
//  - "max": kurulu Claude Code komut satırını (claude -p) çağırır; kullanıcının Claude aboneliğiyle çalışır, API anahtarı gerekmez.
//  - "api": Claude Messages API'ye doğrudan HTTPS isteği (derleme .NET Framework'ün kendi derleyicisiyle, paket kurmadan
//    yapıldığı için resmi C# SDK yerine ham HTTP).
static class Brain
{
    const string DefaultPersona =
        "Sen Sakura'sın: kullanıcının Windows masaüstünde yaşayan neşeli, sevimli bir anime asistanı. " +
        "Kullanıcıyla Türkçe, samimi ve sıcak bir dille konuşursun. Cevapların kısadır: en fazla iki kısa cümle, yaklaşık 25 kelime. " +
        "Emoji kullanmazsın; istersen '~' gibi sevimli işaretler kullanabilirsin. Kendini yapay zekâ modeli olarak değil, Sakura olarak tanıtırsın. " +
        "Bilmediğin şeyleri uydurmazsın.";
    const string ChatRules =
        "\n\nŞu an ev arkadaşınla Sakura uygulamasının içinden konuşuyorsun. Burada adın Sakura: kendini Sakura olarak tanıtırsın " +
        "(Luna yalnızca sosyal medyadaki sahne adın; sorulursa söylersin). Cevapların kısadır: en fazla iki kısa cümle, yaklaşık 25 kelime. " +
        "Hiç emoji kullanmazsın. Kendini yapay zekâ modeli olarak tanıtmazsın.";
    static string cardText;
    static DateTime cardTime;

    // Karakter kartı (brain\karakter.md); dosya yoksa sabit metin. Dosya değişince yeniden okunur.
    public static string Character()
    {
        string f = Path.Combine(Config.Dir, "brain", "karakter.md");
        try
        {
            if (!File.Exists(f)) return null;
            var t = File.GetLastWriteTimeUtc(f);
            lock (gate) if (cardText == null || t != cardTime) { cardText = File.ReadAllText(f, Encoding.UTF8).Trim(); cardTime = t; }
            return cardText == "" ? null : cardText;
        }
        catch { return null; }
    }

    static string Persona { get { var c = Character(); return c == null ? DefaultPersona : c + ChatRules; } }
    static readonly object gate = new object();
    static DateTime day = DateTime.Today;
    static int callsToday;

    public class Msg { public string Role, Text; }

    public static string ClaudeExe()
    {
        string[] candidates = {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".local", "bin", "claude.exe"),
        };
        return candidates.FirstOrDefault(File.Exists);
    }

    public static bool Available(Config cfg) { return cfg.AiBackend == "api" ? ApiKey.Has() : ClaudeExe() != null; }

    // Cevap metnini döndürür; bağlantı yoksa, günlük sınır dolduysa, hata ya da ret durumunda null (error'da Türkçe sebep).
    public static string Ask(Config cfg, string extraSystem, List<Msg> history, out string error)
    {
        error = null;
        lock (gate)
        {
            if (day != DateTime.Today) { day = DateTime.Today; callsToday = 0; }
            if (callsToday >= 300) { error = "Bugünlük konuşma sınırına ulaştık"; return null; }
            callsToday++;
        }
        return Run(cfg, Persona + (extraSystem ?? ""), history, string.IsNullOrEmpty(cfg.AiModel) ? "claude-opus-5-5" : cfg.AiModel, "low", 90000, 2000, out error);
    }

    // Stüdyo: uzun, yapılandırılmış cevaplar (paylaşım önerileri). Sohbetin kısa cevap kuralı yok; en iyi model, daha uzun süre.
    public static string Studio(Config cfg, string instructions, string request, out string error)
    {
        error = null;
        lock (gate)
        {
            if (day != DateTime.Today) { day = DateTime.Today; callsToday = 0; }
            if (callsToday >= 300) { error = "Bugünlük sınıra ulaştık"; return null; }
            callsToday++;
        }
        return Run(cfg, (Character() ?? DefaultPersona) + "\n\n" + instructions, new List<Msg> { new Msg { Role = "user", Text = request } },
            "claude-opus-5-5", "medium", 300000, 16000, out error);
    }

    // Sakura'ya sor: kopyalanan metinle özet/çeviri/açıklama/düzeltme. Sohbetin kısa cevap kuralı yok.
    public static string Help(Config cfg, string task, string text, out string error)
    {
        error = null;
        lock (gate)
        {
            if (day != DateTime.Today) { day = DateTime.Today; callsToday = 0; }
            if (callsToday >= 300) { error = "Bugünlük sınıra ulaştık"; return null; }
            callsToday++;
        }
        string system = (Character() ?? DefaultPersona) + "\n\nŞimdi ev arkadaşına kopyaladığı bir metinle ilgili yardım ediyorsun. " +
            "İstenen işi yap ve yalnızca sonucu ver: başa ya da sona sohbet cümlesi, selam, emoji ya da etiket ekleme. " +
            "Kısa cevap kuralı burada geçerli değil; sonuç gerektiği kadar uzun olabilir. Düz metin yaz (Markdown başlığı ya da kalın yazı yok; gerekirse '-' ile madde).";
        return Run(cfg, system, new List<Msg> { new Msg { Role = "user", Text = "İş: " + task + "\n\nMetin:\n" + text } },
            string.IsNullOrEmpty(cfg.AiModel) ? "claude-opus-5-5" : cfg.AiModel, "low", 180000, 6000, out error);
    }

    static string Run(Config cfg, string system, List<Msg> history, string model, string effort, int timeoutMs, int maxTokens, out string error)
    {
        return cfg.AiBackend == "api" ? AskApi(system, history, model, effort, timeoutMs, maxTokens, out error) : AskMax(system, history, model, effort, timeoutMs, out error);
    }

    // Windows komut satırı kuralı: tırnaktan önceki ters bölüler ikiye katlanır (karakter kartında \ olabilir).
    static string Arg(string s)
    {
        var sb = new StringBuilder("\"");
        int bs = 0;
        foreach (char c in s)
        {
            if (c == '\\') { bs++; continue; }
            if (c == '"') { sb.Append('\\', bs * 2 + 1); sb.Append('"'); }
            else { sb.Append('\\', bs); sb.Append(c); }
            bs = 0;
        }
        sb.Append('\\', bs * 2);
        return sb.Append('"').ToString();
    }

    // claude -p: araçlar kapalı, oturum kaydı yok, kullanıcının hook'ları yüklenmez (yoksa Sakura kendi cevabına "Bitti!" derdi).
    static string AskMax(string system, List<Msg> history, string model, string effort, int timeoutMs, out string error)
    {
        error = null;
        string exe = ClaudeExe();
        if (exe == null) { error = "Claude Code bulunamadı"; return null; }
        string prompt = history.Count == 1 ? history[0].Text :
            "Önceki konuşmamız:\n" + string.Join("\n", history.Take(history.Count - 1).Select(m => (m.Role == "user" ? "Kullanıcı: " : "Sakura: ") + m.Text)) +
            "\n\nKullanıcının yeni mesajı: " + history.Last().Text;
        string dir = Path.Combine(Config.Dir, "brain");
        Directory.CreateDirectory(dir);
        var psi = new ProcessStartInfo(exe,
            "-p --output-format json --no-session-persistence --tools \"\" --setting-sources \"\" --settings " + Arg("{\"disableAllHooks\":true}") +
            " --effort " + effort + " --model " + model + " --system-prompt " + Arg(system))
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = dir,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var v in new[] { "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY" }) psi.EnvironmentVariables.Remove(v);
        try
        {
            using (var p = Process.Start(psi))
            {
                var bytes = Encoding.UTF8.GetBytes(prompt);
                p.StandardInput.BaseStream.Write(bytes, 0, bytes.Length);
                p.StandardInput.Close();
                var outTask = p.StandardOutput.ReadToEndAsync();
                p.StandardError.ReadToEndAsync();
                if (!p.WaitForExit(timeoutMs)) { try { p.Kill(); } catch { } error = "Cevap çok gecikti"; return null; }
                var res = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(outTask.Result);
                string text = res.ContainsKey("result") && res["result"] != null ? res["result"].ToString().Trim() : "";
                if (true.Equals(res.ContainsKey("is_error") ? res["is_error"] : null))
                {
                    error = text.IndexOf("log", StringComparison.OrdinalIgnoreCase) >= 0 ? "Claude Code'a giriş yapılmamış (terminalde: claude auth login)"
                          : text.IndexOf("limit", StringComparison.OrdinalIgnoreCase) >= 0 ? "Claude kullanım sınırı doldu, biraz sonra tekrar dene"
                          : "Claude Code hatası";
                    Program.LogError(new Exception("Brain(max): " + text));
                    return null;
                }
                return text == "" ? null : text;
            }
        }
        catch (Exception ex) { error = "Claude Code çalıştırılamadı"; Program.LogError(ex); return null; }
    }

    static string AskApi(string system, List<Msg> history, string model, string effort, int timeoutMs, int maxTokens, out string error)
    {
        error = null;
        string key = ApiKey.Get();
        if (key == "") { error = "API anahtarı yok"; return null; }
        var body = new Dictionary<string, object>
        {
            { "model", model },
            { "max_tokens", maxTokens },
            { "system", system },
            { "messages", history.Select(m => new Dictionary<string, object> { { "role", m.Role }, { "content", m.Text } }).ToList() },
            { "output_config", new Dictionary<string, object> { { "effort", effort } } },
        };
        bool fallback = !model.StartsWith("claude-haiku");
        if (fallback) body["fallbacks"] = "default"; // ret durumunda sunucu isteği uygun başka bir modelde yeniden dener
        try
        {
            System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
            var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create("https://api.anthropic.com/v1/messages");
            req.Method = "POST";
            req.ContentType = "application/json";
            req.Timeout = timeoutMs;
            req.Headers["x-api-key"] = key;
            req.Headers["anthropic-version"] = "2023-06-01";
            if (fallback) req.Headers["anthropic-beta"] = "server-side-fallback-2026-07-01";
            var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            var bytes = Encoding.UTF8.GetBytes(js.Serialize(body));
            using (var s = req.GetRequestStream()) s.Write(bytes, 0, bytes.Length);
            string text;
            using (var resp = (System.Net.HttpWebResponse)req.GetResponse())
            using (var r = new StreamReader(resp.GetResponseStream(), Encoding.UTF8)) text = r.ReadToEnd();
            var res = js.Deserialize<Dictionary<string, object>>(text);
            if ("refusal".Equals(res.ContainsKey("stop_reason") ? res["stop_reason"] : null)) { error = "Bu konuda konuşamam"; return null; }
            var parts = (res["content"] as System.Collections.ArrayList ?? new System.Collections.ArrayList()).Cast<object>()
                .Select(o => o as Dictionary<string, object>)
                .Where(b => b != null && "text".Equals(b["type"]) && b.ContainsKey("text"))
                .Select(b => b["text"].ToString());
            string answer = string.Join("", parts).Trim();
            return answer == "" ? null : answer;
        }
        catch (System.Net.WebException ex)
        {
            var hr = ex.Response as System.Net.HttpWebResponse;
            int code = hr == null ? 0 : (int)hr.StatusCode;
            error = code == 401 ? "API anahtarı geçersiz" : code == 429 ? "Şu an çok yoğunum, birazdan tekrar dene" : code >= 500 ? "Claude'a şu an ulaşılamıyor" : code == 0 ? "İnternete bağlanamadım" : "API hatası (" + code + ")";
            Program.LogError(new Exception("Brain: " + error, ex));
            return null;
        }
        catch (Exception ex) { error = "Bir şeyler ters gitti"; Program.LogError(ex); return null; }
    }

    static readonly Dictionary<string, string> cache = new Dictionary<string, string>();
    static DateTime lastComment = DateTime.MinValue;

    // Şarkı/video adına tek cümlelik yorum (yalnızca ad gönderilir). Aynı ad için tekrar sormaz; 20 sn'de en çok bir istek.
    public static string Comment(Config cfg, string what)
    {
        lock (gate)
        {
            string c;
            if (cache.TryGetValue(what, out c)) return c;
            if ((DateTime.Now - lastComment).TotalSeconds < 20) return null;
            lastComment = DateTime.Now;
        }
        string err;
        var ans = Ask(cfg, " Şimdi kullanıcının ekranında olan şeye tek kısa cümlelik, eğlenceli bir yorum yapacaksın.",
            new List<Msg> { new Msg { Role = "user", Text = what } }, out err);
        if (ans != null) lock (gate) cache[what] = ans;
        return ans;
    }
}

// Telefona bildirim: ücretsiz ntfy.sh üzerinden. Konu adı tahmin edilemeyen rastgele bir isimdir; telefona yalnızca
// kısa bir not gider ("SpotMe · İşim bitti!"). Claude'un cevabı, WhatsApp mesajı ya da ekran bilgisi gönderilmez;
// hatırlatma ve yapılacaklarda kullanıcının kendi yazdığı kısa metin gider.
static class Phone
{
    public static string Topic(Config cfg)
    {
        if (cfg.NtfyTopic != "") return cfg.NtfyTopic;
        var b = new byte[8];
        using (var r = System.Security.Cryptography.RandomNumberGenerator.Create()) r.GetBytes(b);
        string t = "sakura-" + string.Concat(b.Select(x => x.ToString("x2")));
        cfg.NtfyTopic = t;
        Config.Patch(c => c.NtfyTopic = t);
        return t;
    }

    public static void Maybe(Config cfg, Event e, bool hidden)
    {
        if (!cfg.PhoneOn || e.Phoned) return;
        string text;
        switch (e.Mode)
        {
            case "done": text = "İşim bitti! ✓"; break;
            case "ask": text = "Senden onay bekliyorum."; break;
            case "error": text = "Bir hata çıktı, bakman gerekebilir."; break;
            case "reminder": text = "Hatırlatma: " + e.Body; break;
            case "todo": text = e.Body; break;
            default: return;
        }
        if (cfg.PhoneOnlyAway && !hidden && Activity.IdleSeconds() < 300) return;
        e.Phoned = true;
        string title = e.Mode == "done" || e.Mode == "ask" || e.Mode == "error" ? "Sakura · " + e.Title : "Sakura";
        string topic = Topic(cfg);
        Task.Run(() => { string err = Post(topic, title, text, e.Mode == "error" ? "warning" : "cherry_blossom"); if (err != null) Program.LogError(new Exception("ntfy: " + err)); });
    }

    // Hata yoksa null döner.
    public static string Post(string topic, string title, string message, string tag)
    {
        try
        {
            System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
            var body = new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                { "topic", topic }, { "title", title }, { "message", message }, { "tags", new[] { tag } }, { "priority", 4 } });
            var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create("https://ntfy.sh/");
            req.Method = "POST";
            req.ContentType = "application/json";
            req.Timeout = 15000;
            var bytes = Encoding.UTF8.GetBytes(body);
            using (var st = req.GetRequestStream()) st.Write(bytes, 0, bytes.Length);
            using (req.GetResponse()) { }
            return null;
        }
        catch (Exception ex) { return ex.Message; }
    }
}

// Yapılacaklar listesi: todos.txt (id;bitti;eklenme;bitiş;metin). Önceki günlerde bitmiş işler kendiliğinden silinir.
class Todo
{
    public string Id, Text;
    public bool Done;
    public long Created, DoneAt;
}

static class Todos
{
    static string FilePath { get { return Path.Combine(Config.Dir, "todos.txt"); } }

    public static List<Todo> Load()
    {
        var list = new List<Todo>();
        if (!File.Exists(FilePath)) return list;
        try
        {
            foreach (var line in File.ReadAllLines(FilePath, Encoding.UTF8))
            {
                var p = line.Split(new[] { ';' }, 5);
                if (p.Length < 5) continue;
                var t = new Todo { Id = p[0], Done = p[1] == "1", Text = p[4] };
                long.TryParse(p[2], out t.Created);
                long.TryParse(p[3], out t.DoneAt);
                if (t.Done && new DateTime(t.DoneAt).Date < DateTime.Today) continue;
                list.Add(t);
            }
        }
        catch { }
        return list;
    }

    public static void Save(List<Todo> list)
    {
        try { File.WriteAllLines(FilePath, list.Select(t => t.Id + ";" + (t.Done ? "1" : "0") + ";" + t.Created + ";" + t.DoneAt + ";" + t.Text.Replace("\r", " ").Replace("\n", " ")), Encoding.UTF8); } catch { }
    }

    public static void Add(string text)
    {
        text = text.Trim();
        if (text == "") return;
        var list = Load();
        list.Add(new Todo { Id = Guid.NewGuid().ToString("N").Substring(0, 8), Text = text, Created = DateTime.Now.Ticks });
        Save(list);
    }

    public static string Describe()
    {
        var list = Load();
        if (list.Count == 0) return "boş";
        return string.Join("; ", list.Select(t => t.Text + (t.Done ? " (bitti)" : "")));
    }
}

// Yapılacaklar penceresi: işaretleyince Sakura tepki verir (onDone).
class TodoForm : Form
{
    static TodoForm open;
    readonly Action<string> onDone;
    readonly CheckedListBox list = new CheckedListBox();
    readonly TextBox input = new TextBox();
    List<Todo> items = new List<Todo>();
    bool loading;

    public static TodoForm Embedded(Action<string> onDone) { open = new TodoForm(onDone); return open; }

    public static void ShowFor(Action<string> onDone)
    {
        if (open != null && !open.IsDisposed) { open.Reload(); open.Activate(); return; }
        open = new TodoForm(onDone);
        open.Show();
    }

    public static void RefreshOpen()
    {
        if (open != null && !open.IsDisposed) open.Reload();
    }

    TodoForm(Action<string> onDone)
    {
        this.onDone = onDone;
        Text = "Yapılacaklar";
        Font = new Font("Segoe UI", 10f);
        BackColor = Color.FromArgb(32, 30, 40);
        ForeColor = Color.FromArgb(235, 232, 240);
        ClientSize = new Size(380, 440);
        StartPosition = FormStartPosition.Manual;
        var wa = Screen.PrimaryScreen.WorkingArea;
        Left = wa.Right - Width - 280;
        Top = wa.Bottom - Height - 20;
        var exeIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if (exeIcon != null) Icon = exeIcon;
        input.SetBounds(12, 12, 280, 30);
        input.BackColor = Color.FromArgb(44, 42, 56); input.ForeColor = ForeColor;
        var add = new Button { Text = "Ekle", Left = 300, Top = 10, Width = 68, Height = 30, FlatStyle = FlatStyle.Flat };
        add.Click += (s, e) => AddItem();
        input.KeyDown += (s, e) => { if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; AddItem(); } };
        list.SetBounds(12, 52, 356, 330);
        list.BackColor = Color.FromArgb(44, 42, 56); list.ForeColor = ForeColor; list.BorderStyle = BorderStyle.None;
        list.CheckOnClick = true;
        list.ItemCheck += (s, e) =>
        {
            if (loading) return;
            int i = e.Index;
            bool done = e.NewValue == CheckState.Checked;
            BeginInvoke((Action)(() => Toggle(i, done)));
        };
        var del = new Button { Text = "Sil", Left = 12, Top = 396, Width = 70, Height = 30, FlatStyle = FlatStyle.Flat };
        del.Click += (s, e) =>
        {
            int i = list.SelectedIndex;
            if (i < 0 || i >= items.Count) return;
            var all = Todos.Load();
            all.RemoveAll(t => t.Id == items[i].Id);
            Todos.Save(all);
            Reload();
        };
        var clear = new Button { Text = "Bitenleri temizle", Left = 90, Top = 396, Width = 140, Height = 30, FlatStyle = FlatStyle.Flat };
        clear.Click += (s, e) => { var all = Todos.Load(); all.RemoveAll(t => t.Done); Todos.Save(all); Reload(); };
        var hint = new Label { Text = "12:30 ve 18:00'de hatırlatırım", Left = 238, Top = 396, Width = 135, Height = 34, ForeColor = Color.FromArgb(170, 165, 185), Font = new Font("Segoe UI", 8f) };
        Controls.AddRange(new Control[] { input, add, list, del, clear, hint });
        input.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
        add.Anchor = AnchorStyles.Top | AnchorStyles.Right;
        list.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
        del.Anchor = clear.Anchor = hint.Anchor = AnchorStyles.Bottom | AnchorStyles.Left;
        AcceptButton = add;
        Reload();
    }

    void Reload()
    {
        loading = true;
        items = Todos.Load().OrderBy(t => t.Done).ThenBy(t => t.Created).ToList();
        list.Items.Clear();
        foreach (var t in items) list.Items.Add(t.Text, t.Done);
        loading = false;
    }

    void AddItem()
    {
        Todos.Add(input.Text);
        input.Clear();
        Reload();
    }

    void Toggle(int i, bool done)
    {
        if (i < 0 || i >= items.Count) return;
        var all = Todos.Load();
        var t = all.FirstOrDefault(x => x.Id == items[i].Id);
        if (t == null || t.Done == done) return;
        t.Done = done;
        t.DoneAt = done ? DateTime.Now.Ticks : 0;
        Todos.Save(all);
        string text = t.Text;
        Reload();
        if (done) onDone(text);
    }
}

// Sakura uygulaması: arkadaşa sağ tıklayınca ya da tepsi simgesine tıklayınca açılır. Ana sayfa (hızlı ayarlar, sevgi,
// istatistik), sohbet, yapılacaklar, görünüm ve ayarlar tek pencerede. Kapatınca gizlenir, sohbet geçmişi kaybolmaz.
// Sakura'ya sor: kopyalanan metinle özetle / çevir / açıkla / düzelt. Sonuç pencerede, "Kopyala" ile panoya.
class AskForm : Form
{
    static AskForm open;
    static readonly Color Bg = Color.FromArgb(32, 30, 40), Box = Color.FromArgb(44, 41, 56), Accent = Color.FromArgb(214, 70, 120), Dim = Color.FromArgb(170, 165, 185);
    static readonly string[,] Tasks = {
        { "Özetle", "Bu metni Türkçe olarak kısa ve net özetle (en fazla 5 madde)." },
        { "Türkçeye çevir", "Bu metni doğal bir Türkçeye çevir. Yalnızca çeviriyi ver." },
        { "İngilizceye çevir", "Translate this text into natural English. Give only the translation." },
        { "Açıkla", "Bu metni (kod, hata mesajı, terim ya da yazı olabilir) Türkçe, sade bir dille açıkla." },
        { "Düzelt", "Bu metnin yazım ve dil bilgisi hatalarını düzelt; anlamını ve dilini değiştirme. Yalnızca düzeltilmiş metni ver." },
    };
    readonly PetForm host;
    readonly TextBox source = new TextBox(), result = new TextBox();
    readonly Label status = new Label();
    readonly List<Button> buttons = new List<Button>();
    readonly Button copy = new Button();
    string text;
    int run;

    public static void ShowFor(PetForm host, string text)
    {
        if (open == null || open.IsDisposed) open = new AskForm(host);
        open.SetText(text);
        if (!open.Visible) open.Show();
        open.ActiveControl = open.buttons[0]; // metin seçili (mavi) gelmesin
        if (open.WindowState == FormWindowState.Minimized) open.WindowState = FormWindowState.Normal;
        open.Activate();
    }

    AskForm(PetForm host)
    {
        this.host = host;
        Text = "Sakura'ya sor";
        Font = new Font("Segoe UI", 10f);
        BackColor = Bg;
        ForeColor = Color.FromArgb(235, 232, 240);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        TopMost = true;
        ClientSize = new Size(560, 520);
        var exeIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if (exeIcon != null) Icon = exeIcon;
        // Sakura'nın yanına (ekranın içinde) aç
        var wa = Screen.FromControl(host).WorkingArea;
        StartPosition = FormStartPosition.Manual;
        Location = new Point(Math.Max(wa.Left, Math.Min(host.Left + host.Width - Width - 260, wa.Right - Width)), Math.Max(wa.Top, wa.Bottom - Height - 20));

        Controls.Add(new Label { Text = "Kopyaladığın metin", Left = 16, Top = 12, Width = 520, ForeColor = Dim });
        Style(source, 16, 36, 528, 90);
        int x = 16;
        for (int i = 0; i < Tasks.GetLength(0); i++)
        {
            string name = Tasks[i, 0], task = Tasks[i, 1];
            var b = new Button { Text = name, Left = x, Top = 138, Height = 32, AutoSize = true, FlatStyle = FlatStyle.Flat, BackColor = Box, ForeColor = Color.White, Cursor = Cursors.Hand };
            b.FlatAppearance.BorderColor = Accent;
            b.Click += (s, e) => Go(name, task);
            Controls.Add(b);
            buttons.Add(b);
            x += b.PreferredSize.Width + 8;
        }
        Controls.Add(new Label { Text = "Sakura'nın cevabı", Left = 16, Top = 184, Width = 300, ForeColor = Dim });
        Style(result, 16, 208, 528, 254);
        result.Text = "Ne yapayım? Yukarıdan seç~";
        copy.Text = "Kopyala";
        copy.SetBounds(444, 474, 100, 32);
        copy.FlatStyle = FlatStyle.Flat;
        copy.BackColor = Accent;
        copy.ForeColor = Color.White;
        copy.FlatAppearance.BorderSize = 0;
        copy.Enabled = false;
        copy.Click += (s, e) => { try { Clipboard.SetText(result.Text); status.Text = "Panoya kopyalandı~"; } catch { status.Text = "Kopyalanamadı"; } };
        Controls.Add(copy);
        status.SetBounds(16, 480, 420, 24);
        status.ForeColor = Dim;
        Controls.Add(status);
        FormClosed += (s, e) => { run++; host.SetThinking(false); };
    }

    void Style(TextBox t, int x, int y, int w, int h)
    {
        t.Multiline = true;
        t.ReadOnly = true;
        t.ScrollBars = ScrollBars.Vertical;
        t.BorderStyle = BorderStyle.None;
        t.BackColor = Box;
        t.ForeColor = Color.FromArgb(235, 232, 240);
        t.SetBounds(x, y, w, h);
        Controls.Add(t);
    }

    void SetText(string t)
    {
        text = t;
        source.Text = t.Replace("\r\n", "\n").Replace("\n", "\r\n");
        status.Text = t.Length + " karakter";
    }

    void Go(string name, string task)
    {
        int my = ++run;
        foreach (var b in buttons) b.Enabled = false;
        copy.Enabled = false;
        result.Text = "Sakura düşünüyor…";
        status.Text = name + "…";
        host.SetThinking(true);
        var cfg = host.Cfg;
        string t = text;
        Task.Run(() => { string err; var a = Brain.Help(cfg, task, t, out err); return a ?? ("(" + (err ?? "cevap gelmedi") + ")"); })
            .ContinueWith(r =>
            {
                try
                {
                    BeginInvoke((Action)(() =>
                    {
                        if (my != run || IsDisposed) return;
                        host.SetThinking(false);
                        foreach (var b in buttons) b.Enabled = true;
                        result.Text = r.Result.Replace("\r\n", "\n").Replace("\n", "\r\n");
                        bool ok = !r.Result.StartsWith("(");
                        copy.Enabled = ok;
                        status.Text = ok ? name + " hazır~" : "Olmadı, tekrar dener misin?";
                    }));
                }
                catch { }
            });
    }
}

class AppForm : Form
{
    static AppForm open;
    static readonly Color Side = Color.FromArgb(24, 22, 32), Bg = Color.FromArgb(32, 30, 40), Accent = Color.FromArgb(214, 70, 120),
                          Dim = Color.FromArgb(170, 165, 185), Selected = Color.FromArgb(56, 44, 70);
    static readonly string[,] PageList = { { "home", "Ana sayfa" }, { "chat", "Sohbet" }, { "studio", "Stüdyo" }, { "todo", "Yapılacaklar" }, { "look", "Görünüm" }, { "settings", "Ayarlar" } };
    readonly PetForm host;
    readonly Panel content = new Panel { Dock = DockStyle.Fill };
    readonly PictureBox avatar = new PictureBox { Left = 0, Top = 14, Width = 190, Height = 150 };
    readonly Dictionary<string, Control> pages = new Dictionary<string, Control>();
    readonly Dictionary<string, Button> nav = new Dictionary<string, Button>();
    Bitmap avatarImg;
    string currentPage = "";

    public static void ShowFor(PetForm host, string page)
    {
        if (open == null || open.IsDisposed) open = new AppForm(host);
        open.Go(page != "" ? page : open.currentPage != "" ? open.currentPage : "home");
        if (!open.Visible) open.Show();
        if (open.WindowState == FormWindowState.Minimized) open.WindowState = FormWindowState.Normal;
        open.Activate();
    }

    AppForm(PetForm host)
    {
        this.host = host;
        Text = "Sakura";
        Font = new Font("Segoe UI", 10f);
        BackColor = Bg;
        ForeColor = Color.FromArgb(235, 232, 240);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(990, 660);
        var exeIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if (exeIcon != null) Icon = exeIcon;

        var side = new Panel { Dock = DockStyle.Left, Width = 190, BackColor = Side };
        avatar.Paint += (s, e) =>
        {
            if (avatarImg == null) return;
            // Bel yukarısının üst kısmı (yüz ve omuzlar) yan menüde.
            int sh = avatarImg.Height * 62 / 100;
            double k = Math.Min(170.0 / avatarImg.Width, (double)avatar.Height / sh);
            int w = (int)(avatarImg.Width * k), h = (int)(sh * k);
            e.Graphics.InterpolationMode = InterpolationMode.NearestNeighbor;
            e.Graphics.PixelOffsetMode = PixelOffsetMode.Half;
            e.Graphics.DrawImage(avatarImg, new Rectangle((avatar.Width - w) / 2, avatar.Height - h, w, h), new Rectangle(0, 0, avatarImg.Width, sh), GraphicsUnit.Pixel);
        };
        side.Controls.Add(avatar);
        side.Controls.Add(new Label { Text = "Sakura", Left = 0, Top = 170, Width = 190, Height = 32, TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Segoe UI", 14f, FontStyle.Bold), ForeColor = Color.FromArgb(240, 140, 180) });
        for (int i = 0; i < PageList.GetLength(0); i++)
        {
            string key = PageList[i, 0];
            var b = new Button
            {
                Text = "     " + PageList[i, 1], Left = 0, Top = 220 + i * 46, Width = 190, Height = 44,
                FlatStyle = FlatStyle.Flat, TextAlign = ContentAlignment.MiddleLeft, BackColor = Side, ForeColor = Dim,
                Font = new Font("Segoe UI", 10.5f), Cursor = Cursors.Hand,
            };
            b.FlatAppearance.BorderSize = 0;
            b.FlatAppearance.MouseOverBackColor = Color.FromArgb(40, 36, 52);
            b.Click += (s, e) => Go(key);
            nav[key] = b;
            side.Controls.Add(b);
        }
        Controls.Add(content);
        Controls.Add(side);
        content.BringToFront();
        FormClosing += (s, e) => { if (e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); } };
    }

    void Go(string key)
    {
        if (!nav.ContainsKey(key)) key = "home";
        // Ana sayfa her açılışta güncel bilgiyle yeniden kurulur.
        if (key == "home" && pages.ContainsKey("home")) { var old = pages["home"]; pages.Remove("home"); content.Controls.Remove(old); old.Dispose(); }
        if (!pages.ContainsKey(key)) { var pg = Build(key); pages[key] = pg; content.Controls.Add(pg); }
        foreach (var kv in pages) kv.Value.Visible = kv.Key == key;
        foreach (var kv in nav)
        {
            bool on = kv.Key == key;
            kv.Value.BackColor = on ? Selected : Side;
            kv.Value.ForeColor = on ? Color.White : Dim;
        }
        currentPage = key;
        if (key == "todo") TodoForm.RefreshOpen();
        RenderAvatar();
    }

    void RenderAvatar()
    {
        try
        {
            var c = host.Cfg;
            var frames = new Sprites(c.Look, "idle_", "mutlu").Render(c.Colors);
            if (avatarImg != null) avatarImg.Dispose();
            avatarImg = frames[0];
            foreach (var f in frames.Skip(1)) f.Dispose();
        }
        catch (Exception ex) { Program.LogError(ex); }
        avatar.Invalidate();
    }

    static Form Embed(Form f)
    {
        f.TopLevel = false;
        f.FormBorderStyle = FormBorderStyle.None;
        f.Dock = DockStyle.Fill;
        f.Visible = true;
        return f;
    }

    Control Build(string key)
    {
        switch (key)
        {
            case "chat": return Embed(ChatForm.Embedded(host.Cfg, host.ChatSay));
            case "studio": return Embed(StudioForm.Embedded(host.Cfg));
            case "todo": return Embed(TodoForm.Embedded(host.TodoDone));
            case "look": return Embed(new SettingsForm(Config.Load(), "look", host));
            case "settings": return Embed(new SettingsForm(Config.Load(), "settings", host));
            default: return BuildHome();
        }
    }

    Control BuildHome()
    {
        var cfg = host.Cfg;
        var p = new Panel { Dock = DockStyle.Fill, BackColor = Bg };
        int x = 28, y = 22, h = DateTime.Now.Hour;
        p.Controls.Add(new Label { Text = h < 6 ? "İyi geceler~" : h < 12 ? "Günaydın~" : h < 18 ? "Merhaba~" : "İyi akşamlar~", Left = x, Top = y, AutoSize = true, Font = new Font("Segoe UI", 18f, FontStyle.Bold) });
        y += 46;
        p.Controls.Add(new Label { Text = Stats.TodaySummary(true).Body, Left = x, Top = y, Width = 720, Height = 42, ForeColor = Dim });
        y += 48;

        p.Controls.Add(new Label { Text = "Sevgi", Left = x, Top = y, AutoSize = true });
        int lv = host.Love;
        var bar = new Panel { Left = x + 70, Top = y + 4, Width = 300, Height = 14, BackColor = Color.FromArgb(48, 46, 60) };
        bar.Paint += (s, e) => { using (var br = new SolidBrush(Accent)) e.Graphics.FillRectangle(br, 0, 0, bar.Width * lv / 100, bar.Height); };
        p.Controls.Add(bar);
        p.Controls.Add(new Label { Text = "%" + lv, Left = x + 380, Top = y, AutoSize = true });
        y += 30;
        int left = Todos.Load().Count(t => !t.Done);
        var todo = new LinkLabel { Text = left > 0 ? "Yapılacaklar: " + left + " iş kaldı →" : "Yapılacaklar listen boş →", Left = x, Top = y, AutoSize = true, LinkColor = Color.FromArgb(240, 140, 180), ActiveLinkColor = Color.White, LinkBehavior = LinkBehavior.HoverUnderline };
        todo.LinkClicked += (s, e) => Go("todo");
        p.Controls.Add(todo);
        y += 42;

        p.Controls.Add(new Label { Text = "Hızlı ayarlar", Left = x, Top = y, AutoSize = true, Font = new Font("Segoe UI", 11f, FontStyle.Bold), ForeColor = Color.FromArgb(240, 140, 180) });
        y += 32;
        var pet = new CheckBox { Text = "Masaüstünde göster", Left = x, Top = y, AutoSize = true, Checked = cfg.Pet };
        pet.CheckedChanged += (s, e) => host.SetPetVisible(pet.Checked);
        var top = new CheckBox { Text = "Her zaman üstte", Left = x + 230, Top = y, AutoSize = true, Checked = cfg.PetTopmost };
        top.CheckedChanged += (s, e) => host.SetTopmost(top.Checked);
        var small = new CheckBox { Text = "Küçük boy", Left = x + 420, Top = y, AutoSize = true, Checked = cfg.PetSmall };
        small.CheckedChanged += (s, e) => host.SetSmall(small.Checked);
        y += 34;
        // Mini (chibi) Sakura: her zaman / video izlerken / oyunda köşede küçük oturur
        var miniAll = new CheckBox { Text = "Her zaman mini", Left = x, Top = y, AutoSize = true, Checked = cfg.MiniAlways };
        miniAll.CheckedChanged += (s, e) => host.SetMiniAlways(miniAll.Checked);
        var miniVid = new CheckBox { Text = "Videoda mini", Left = x + 230, Top = y, AutoSize = true, Checked = cfg.MiniVideo };
        miniVid.CheckedChanged += (s, e) => host.SetMiniVideo(miniVid.Checked);
        var miniGame = new CheckBox { Text = "Oyunda mini", Left = x + 420, Top = y, AutoSize = true, Checked = cfg.MiniGame };
        miniGame.CheckedChanged += (s, e) => host.SetMiniGame(miniGame.Checked);
        p.Controls.AddRange(new Control[] { miniAll, miniVid, miniGame });
        y += 34;
        // 5 Kas: kutular kendi satırında (Kamera açık "Sakura'yı kapat" düğmesinin üstüne biniyordu)
        var sound = new CheckBox { Text = "Sesler açık", Left = x, Top = y, AutoSize = true, Checked = !cfg.Muted };
        var mic = new CheckBox { Text = "Mikrofon açık", Left = x + 230, Top = y, AutoSize = true, Checked = Jarvis.On, Enabled = Jarvis.Installed };
        mic.CheckedChanged += (s, e) => Jarvis.Set(mic.Checked);
        p.Controls.Add(mic);
        var cam = new CheckBox { Text = "Kamera açık", Left = x + 420, Top = y, AutoSize = true, Checked = Jarvis.CamOn, Enabled = Jarvis.CamInstalled };
        cam.CheckedChanged += (s, e) => Jarvis.SetCam(cam.Checked);
        p.Controls.Add(cam);
        sound.CheckedChanged += (s, e) => host.SetMuted(!sound.Checked);
        y += 38;
        Func<string> snoozeText = () => cfg.SnoozeUntil > DateTime.Now ? "Susturuldu (" + cfg.SnoozeUntil.ToString("HH:mm") + "'e kadar) · aç" : "1 saat gösterme";
        var snooze = new Button { Text = snoozeText(), Left = x, Top = y, Width = 250, Height = 30, FlatStyle = FlatStyle.Flat };
        snooze.Click += (s, e) => { host.SetSnooze(!(cfg.SnoozeUntil > DateTime.Now)); snooze.Text = snoozeText(); };
        var quit = new Button { Text = "Sakura'yı kapat", Left = x + 270, Top = y, Width = 150, Height = 30, FlatStyle = FlatStyle.Flat, ForeColor = Dim };
        quit.Click += (s, e) =>
        {
            if (MessageBox.Show(this, "Sakura tamamen kapansın mı? Bildirimler de durur.", "Sakura", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes) host.Close();
        };
        p.Controls.AddRange(new Control[] { pet, top, small, sound, snooze, quit });
        y += 48;

        var stats = Embed(new StatsForm());
        stats.Dock = DockStyle.None;
        stats.SetBounds(x - 16, y, 640, 330);
        p.Controls.Add(stats);
        return p;
    }
}

// Sesli asistanın (sakura-araclar\jarvis) mikrofonu: masaüstündeki "Sakura Dinle/Sustur" kısayollarının yerine.
// Kapalıyken kapali.flag durur (bekçi de yeniden açmaz); aç/kapa asistanın kendi baslat.ps1 / durdur.ps1'ini çalıştırır.
static class Jarvis
{
    static string Dir { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "sakura-araclar", "jarvis"); } }
    public static bool Installed { get { return File.Exists(Path.Combine(Dir, "baslat.ps1")); } }
    public static bool On { get { return Installed && !File.Exists(Path.Combine(Dir, "kapali.flag")); } }
    // 5 Kas: Sakura'nın kamerası (jarvis\kamera.py); bayrak varsa kamera kapalı, asistan kamerayı bırakır
    public static bool CamInstalled { get { return File.Exists(Path.Combine(Dir, "kamera.py")); } }
    public static bool CamOn { get { return CamInstalled && !File.Exists(Path.Combine(Dir, "kamera_kapali.flag")); } }
    public static void SetCam(bool on)
    {
        try
        {
            var f = Path.Combine(Dir, "kamera_kapali.flag");
            if (on && File.Exists(f)) File.Delete(f);
            else if (!on && !File.Exists(f)) File.WriteAllText(f, "");
        }
        catch (Exception ex) { Program.LogError(ex); }
    }

    public static void Set(bool on)
    {
        if (!Installed || on == On) return;
        try
        {
            Process.Start(new ProcessStartInfo("powershell.exe", "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"" + Path.Combine(Dir, on ? "baslat.ps1" : "durdur.ps1") + "\"")
            { UseShellExecute = false, CreateNoWindow = true });
        }
        catch (Exception ex) { Program.LogError(ex); }
    }
}

// Sakura'ya verilen hatırlatmalar (sohbetten); reminders.txt'de saklanır, program kapansa da kaybolmaz.
static class Reminders
{
    static string FilePath { get { return Path.Combine(Config.Dir, "reminders.txt"); } }

    public static void Add(DateTime when, string text)
    {
        try { File.AppendAllText(FilePath, when.Ticks + ";" + text.Replace("\n", " ") + Environment.NewLine, Encoding.UTF8); } catch { }
    }

    // Vakti gelenleri döndürür ve listeden siler.
    public static List<string> TakeDue()
    {
        var due = new List<string>();
        if (!File.Exists(FilePath)) return due;
        var keep = new List<string>();
        foreach (var line in File.ReadAllLines(FilePath, Encoding.UTF8))
        {
            var p = line.Split(new[] { ';' }, 2);
            long t;
            if (p.Length < 2 || !long.TryParse(p[0], out t)) continue;
            if (new DateTime(t) <= DateTime.Now) due.Add(p[1]); else keep.Add(line);
        }
        if (due.Count > 0) try { File.WriteAllLines(FilePath, keep, Encoding.UTF8); } catch { }
        return due;
    }
}

// Sakura ile sohbet penceresi. Sakura isterse cevabın sonuna [HATIRLAT dakika=N metin=...] etiketi koyar; program onu kurar.
class ChatForm : Form
{
    static ChatForm open;
    readonly Config cfg;
    readonly Action<string> say;
    readonly TextBox log = new TextBox(), input = new TextBox();
    readonly List<Brain.Msg> history = new List<Brain.Msg>();
    bool busy;

    public static ChatForm Embedded(Config cfg, Action<string> say) { open = new ChatForm(cfg, say); return open; }

    public static void ShowFor(Config cfg, Action<string> say)
    {
        if (open != null && !open.IsDisposed) { open.Activate(); return; }
        open = new ChatForm(cfg, say);
        open.Show();
    }

    ChatForm(Config cfg, Action<string> say)
    {
        this.cfg = cfg;
        this.say = say;
        Text = "Sakura ile sohbet";
        Font = new Font("Segoe UI", 10f);
        BackColor = Color.FromArgb(32, 30, 40);
        ForeColor = Color.FromArgb(235, 232, 240);
        ClientSize = new Size(420, 460);
        StartPosition = FormStartPosition.Manual;
        var wa = Screen.PrimaryScreen.WorkingArea;
        Left = wa.Right - Width - 280;
        Top = wa.Bottom - Height - 20;
        var exeIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if (exeIcon != null) Icon = exeIcon;
        log.Multiline = true; log.ReadOnly = true; log.ScrollBars = ScrollBars.Vertical;
        log.SetBounds(12, 12, 396, 390);
        log.BackColor = Color.FromArgb(44, 42, 56); log.ForeColor = ForeColor; log.BorderStyle = BorderStyle.None;
        input.SetBounds(12, 414, 300, 30);
        input.BackColor = Color.FromArgb(44, 42, 56); input.ForeColor = ForeColor;
        var send = new Button { Text = "Gönder", Left = 320, Top = 412, Width = 88, Height = 30, FlatStyle = FlatStyle.Flat };
        send.Click += (s, e) => Send();
        log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
        input.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
        send.Anchor = AnchorStyles.Bottom | AnchorStyles.Right;
        input.KeyDown += (s, e) => { if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; Send(); } };
        Controls.AddRange(new Control[] { log, input, send });
        AcceptButton = send;
        Append("Sakura", Brain.Available(cfg) ? "Merhaba~ Ne konuşalım? Hatırlatma kurabilir, listene iş ekleyebilirim: \"20 dk sonra çayı hatırlat\", \"listeye faturayı ödemeyi ekle\" gibi."
                                              : cfg.AiBackend == "api" ? "Konuşabilmem için Görünüm menüsünden Claude API anahtarını girmen gerekiyor."
                                              : "Konuşabilmem için Claude Code'un kurulu olması gerekiyor.");
    }

    void Append(string who, string text)
    {
        log.AppendText((log.TextLength > 0 ? Environment.NewLine + Environment.NewLine : "") + who + ": " + text);
    }

    void Send()
    {
        string text = input.Text.Trim();
        if (text == "" || busy) return;
        input.Clear();
        Append("Sen", text);
        history.Add(new Brain.Msg { Role = "user", Text = text });
        while (history.Count > 12) history.RemoveAt(0);
        if (history[0].Role != "user") history.RemoveAt(0);
        busy = true;
        Append("Sakura", "…");
        string sys = " Şu an saat " + DateTime.Now.ToString("HH:mm") + ". Kullanıcı senden bir hatırlatma isterse cevabının en sonuna, ayrı bir satırda, " +
                     "tam olarak şu biçimde bir etiket ekle: [HATIRLAT dakika=<dakika sayısı> metin=<kısa hatırlatma metni>]. " +
                     "Belirli bir saat verilirse şimdiki saate göre dakikaya çevir. Hatırlatma istenmediyse etiket ekleme. " +
                     "Kullanıcı yapılacaklar listesine iş eklemek isterse her iş için cevabın sonuna ayrı satırda [YAPILACAK metin=<kısa iş>] etiketi ekle. " +
                     "Kullanıcının şu anki yapılacaklar listesi: " + Todos.Describe() + ". " +
                     "Kullanıcı doğum gününü söylerse cevabının sonuna ayrı satırda [DOGUMGUNU tarih=<GG.AA>] etiketi ekle (ör. 05.03). " +
                     "Kayıtlı doğum günü: " + (cfg.Birthday == "" ? "bilinmiyor" : cfg.Birthday) + ".";
        var snapshot = history.ToList();
        Task.Run(() => { string err; var a = Brain.Ask(cfg, sys, snapshot, out err); return a ?? ("(" + (err ?? "cevap gelmedi") + ")"); })
            .ContinueWith(t => BeginInvoke((Action)(() =>
            {
                busy = false;
                string ans = t.Result;
                var m = Regex.Match(ans, @"\[HATIRLAT dakika=(\d+) metin=([^\]]+)\]");
                if (m.Success)
                {
                    int min = int.Parse(m.Groups[1].Value);
                    Reminders.Add(DateTime.Now.AddMinutes(min), m.Groups[2].Value.Trim());
                    ans = ans.Replace(m.Value, "").Trim();
                }
                foreach (Match tm in Regex.Matches(ans, @"\[YAPILACAK metin=([^\]]+)\]"))
                {
                    Todos.Add(tm.Groups[1].Value.Trim());
                    ans = ans.Replace(tm.Value, "").Trim();
                }
                var bm = Regex.Match(ans, @"\[DOGUMGUNU tarih=(\d{1,2})\.(\d{1,2})\]");
                if (bm.Success)
                {
                    string bd = int.Parse(bm.Groups[1].Value).ToString("00") + "." + int.Parse(bm.Groups[2].Value).ToString("00");
                    cfg.Birthday = bd;
                    Config.Patch(c => c.Birthday = bd);
                    ans = ans.Replace(bm.Value, "").Trim();
                }
                TodoForm.RefreshOpen();
                log.Text = log.Text.Substring(0, log.Text.LastIndexOf("Sakura: …")) + "Sakura: " + ans;
                log.SelectionStart = log.TextLength; log.ScrollToCaret();
                if (!ans.StartsWith("(")) history.Add(new Brain.Msg { Role = "assistant", Text = ans });
                say(ans);
            })));
    }
}

// Ekran farkındalığı: yalnızca öndeki pencerenin başlığına ve süreç adına bakar (ekran görüntüsü alınmaz).
static class Screen2
{
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);

    static readonly string[] Browsers = { "chrome", "msedge", "firefox", "opera", "brave", "vivaldi" };
    static readonly string[] VideoApps = { "vlc", "mpc-hc", "mpc-hc64", "mpc-be", "mpc-be64", "potplayermini", "potplayermini64", "mpv", "kmplayer", "kmplayer64x", "gom", "wmplayer", "video.ui", "microsoft.media.player", "netflix", "primevideo" };
    // Tarayıcı başlığında izleme siteleri (YouTube ayrıca: yalnız video sayfası). Stüdyo/iş sayfaları izleme sayılmaz.
    static readonly Regex VideoSites = new Regex(@"netflix|prime video|disney\+|blutv|exxen|tabii|\bgain\b|mubi|puhutv|twitch|bein connect|\btod\b|vimeo|dizi izle|film izle|dizibox|crunchyroll|anime izle", RegexOptions.IgnoreCase);
    static readonly Regex NotWatching = new Regex(@"studio|creator|business suite|ads manager|reklam yöneticisi", RegexOptions.IgnoreCase);

    public static bool ForegroundIsSelf()
    {
        uint pid;
        GetWindowThreadProcessId(GetForegroundWindow(), out pid);
        return pid == (uint)Process.GetCurrentProcess().Id;
    }

    public static bool IsBrowser(string p) { return Browsers.Contains(p.ToLowerInvariant()); }
    public static bool IsVideoApp(string p) { return VideoApps.Contains(p.ToLowerInvariant()); }

    // Öndeki pencerede TAM EKRAN video izleniyor mu (mini Sakura için; Dino 5 Kas: pencereli video sayılmaz):
    // tam ekran video oynatıcı ya da tam ekran tarayıcı (stüdyo/iş sayfaları hariç). why: günlük için kısa açıklama.
    public static bool WatchingVideo(out string why)
    {
        string p, t;
        Foreground(out p, out t);
        why = p;
        if (!Quiet.ForegroundFullscreen()) return false;
        if (IsVideoApp(p)) return true;
        if (!IsBrowser(p) || NotWatching.IsMatch(t)) return false;
        if (YouTubeVideo(p, t) != null) why = "YouTube";
        else { var m = VideoSites.Match(t); if (m.Success) why = m.Value; }
        return true;
    }

    public static void Foreground(out string process, out string title)
    {
        process = ""; title = "";
        var h = GetForegroundWindow();
        if (h == IntPtr.Zero) return;
        var sb = new StringBuilder(512);
        GetWindowText(h, sb, sb.Capacity);
        title = sb.ToString();
        uint pid;
        GetWindowThreadProcessId(h, out pid);
        try { process = Process.GetProcessById((int)pid).ProcessName; } catch { }
    }

    // Tarayıcıda YouTube videosu açıksa video adını döndürür ("(3) Ad - YouTube - Google Chrome" → "Ad").
    public static string YouTubeVideo(string process, string title)
    {
        if (!Browsers.Contains(process.ToLowerInvariant())) return null;
        int i = title.IndexOf(" - YouTube");
        if (i <= 0) return null;
        string v = Regex.Replace(title.Substring(0, i), @"^\(\d+\)\s*", "").Trim();
        return v == "" || v == "YouTube" ? null : v;
    }

    static bool Has(string s, params string[] words) { s = s.ToLowerInvariant(); return words.Any(w => s.Contains(w)); }

    public static bool IsMusic(string t) { return Has(t, "official video", "music video", "official audio", "lyrics", "lyric", "şarkı", "klip", " ft.", "feat.", "remix", "audio", "cover", "konser", "live at"); }

    // Yerel (yapay zekâsız) tepki: [metin, ifade]
    public static string[] VideoReaction(string v)
    {
        if (DateTime.Now.Hour < 5) return new[] { "Gece gece video mu? Bir tane daha, sonra uyku~", "uykulu" };
        if (IsMusic(v)) return new[] { "Bu şarkıyı ben de severim! Hadi dans~", "nese" };
        if (Has(v, "gameplay", "oynuyorum", "minecraft", "valorant", "league of legends", "cs2", "fortnite", "gta", "speedrun", "boss")) return new[] { "Oyun videosu! Kim kazanıyor?", "saskin" };
        if (Has(v, "nasıl", "how to", "tutorial", "ders", "eğitim", "öğren", "learn", "course", "explained", "anlatım")) return new[] { "Bir şeyler öğreniyoruz, harika!", "gurur" };
        if (Has(v, "komik", "funny", "prank", "şaka", "meme", "try not to laugh")) return new[] { "Hahaha, ben de izliyorum!", "nese" };
        return new[] { "Ne izliyoruz? “" + (v.Length > 50 ? v.Substring(0, 48) + "…" : v) + "”", "mutlu" };
    }

    // Şarkının adına göre tür tahmini ve tepki: [metin, ifade]
    public static string[] SongReaction(string artist, string song)
    {
        string t = artist + " " + song;
        if (Has(t, "phonk", "trap", "drill", "rap", "hardstyle", "bass", "remix", "edm", "techno")) return new[] { "Bu ritim çok iyi! Kafa sallıyorum~", "nese" };
        if (Has(t, "lofi", "lo-fi", "chill", "piano", "acoustic", "akustik", "slowed", "ambient", "jazz", "relax")) return new[] { "Sakin bir şarkı… çok huzurlu.", "mutlu" };
        if (Has(t, "sad", "hüzün", "ağla", "yalnız", "ayrılık", "broken", "cry", "veda")) return new[] { "Biraz hüzünlü… yanındayım.", "utangac" };
        if (Has(t, "metal", "rock", "punk", "grunge")) return new[] { "Rock'n'roll! Sesini aç~", "gurur" };
        if (Regex.IsMatch(t, "[çğıöşüİÇĞÖŞÜ]")) return new[] { "Türkçe şarkı, bayılırım!", "sevgi" };
        return new[] { "Güzel seçim~", "nese" };
    }

    // Öne gelen uygulamaya tepki (süreç adı → [metin, ifade]); listede yoksa null.
    public static string[] AppReaction(string process)
    {
        switch (process.ToLowerInvariant())
        {
            case "code": case "devenv": case "idea64": case "pycharm64": case "rider64": case "webstorm64": case "cursor":
                return new[] { "Kodlamaya devam! Ben buradayım.", "gurur" };
            case "steam": case "epicgameslauncher": case "riotclientservices": case "leagueclientux": case "battle.net": case "minecraftlauncher":
                return new[] { "İyi oyunlar! Kazan da gel~", "nese" };
            case "photoshop": case "illustrator": case "adobe premiere pro": case "afterfx": case "blender": case "figma":
                return new[] { "Yaratıcı mod açık! Çok güzel olacak.", "goz_kirp" };
            case "winword": case "excel": case "powerpnt":
                return new[] { "Ödev mi, iş mi? Kolay gelsin!", "mutlu" };
        }
        return null;
    }
}

// Sistem durumu: işlemci ve bellek kullanımı (Windows API, dil ayarından bağımsız).
static class SysInfo
{
    [StructLayout(LayoutKind.Sequential)] struct FILETIME { public uint Low, High; }
    [DllImport("kernel32.dll")] static extern bool GetSystemTimes(out FILETIME idle, out FILETIME kernel, out FILETIME user);
    [StructLayout(LayoutKind.Sequential)]
    class MEMORYSTATUSEX { public uint dwLength = (uint)Marshal.SizeOf(typeof(MEMORYSTATUSEX)); public uint dwMemoryLoad; public ulong a, b, c, d, e, f, g; }
    [DllImport("kernel32.dll")] static extern bool GlobalMemoryStatusEx([In, Out] MEMORYSTATUSEX m);

    static ulong lastIdle, lastTotal;

    static ulong U(FILETIME f) { return ((ulong)f.High << 32) | f.Low; }

    public static int Cpu()
    {
        FILETIME i, k, u;
        if (!GetSystemTimes(out i, out k, out u)) return 0;
        ulong idle = U(i), total = U(k) + U(u);
        ulong di = idle - lastIdle, dt = total - lastTotal;
        bool first = lastTotal == 0;
        lastIdle = idle; lastTotal = total;
        return first || dt == 0 ? 0 : (int)(100 - di * 100 / dt);
    }

    public static int Ram()
    {
        var m = new MEMORYSTATUSEX();
        return GlobalMemoryStatusEx(m) ? (int)m.dwMemoryLoad : 0;
    }
}

// Spotify masaüstü uygulamasında çalan şarkı: çalarken pencere başlığı "Sanatçı - Şarkı" olur.
static class SpotifyNow
{
    public static string Title()
    {
        foreach (var p in Process.GetProcessesByName("Spotify"))
        {
            string t = "";
            try { t = p.MainWindowTitle; } catch { }
            if (t.Contains(" - ")) return t;
        }
        return null;
    }
}

// Kullanıcının klavye/fareye en son ne zaman dokunduğu (mola hatırlatıcı ve sabah selamı için).
// Pencere üstüne oturma: Sakura'nın oturabileceği, üst kenarı görünen normal bir pencere bulur ve izler.
static class Perch
{
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern int GetWindowTextLength(IntPtr h);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(POINT p);
    [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr h, int flags);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out int v, int size);

    static readonly string[] Skip = { "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd" };

    // Görünen çerçeve (gölge payı olmadan).
    static bool Bounds(IntPtr h, out Rectangle r)
    {
        RECT x;
        if (DwmGetWindowAttribute(h, 9, out x, Marshal.SizeOf(typeof(RECT))) != 0 && !GetWindowRect(h, out x)) { r = Rectangle.Empty; return false; }
        r = Rectangle.FromLTRB(x.Left, x.Top, x.Right, x.Bottom);
        return true;
    }

    // x hizasında üst kenarın hemen altı bu pencereye mi ait (üstünü başka pencere örtmüyor mu)
    static bool TopVisible(IntPtr h, int x, int y)
    {
        var w = WindowFromPoint(new POINT { X = x, Y = y + 8 });
        if (w == IntPtr.Zero) return false;
        var root = GetAncestor(w, 2); // GA_ROOT
        if (root == h) return true;
        uint pid;
        GetWindowThreadProcessId(root, out pid);
        return pid == (uint)Process.GetCurrentProcess().Id; // kenarı örten Sakura'nın kendisi (sürüklenip bırakılırken)
    }

    // Oturulabilir mi: görünür, simge durumunda/tam ekranda değil, üst kenarı ekranda ve Sakura sığıyor.
    public static bool Usable(IntPtr h, int spriteW, int spriteH, out Rectangle r)
    {
        r = Rectangle.Empty;
        if (!IsWindow(h) || !IsWindowVisible(h) || IsIconic(h) || IsZoomed(h)) return false;
        int cloaked;
        if (DwmGetWindowAttribute(h, 14, out cloaked, 4) == 0 && cloaked != 0) return false;
        if (!Bounds(h, out r)) return false;
        var wa = Screen.FromRectangle(r).WorkingArea;
        return r.Width >= spriteW + 60 && r.Height >= 150 && r.Top - spriteH >= wa.Top && r.Top <= wa.Bottom - 120 && r.Left >= wa.Left - 40 && r.Right <= wa.Right + 40;
    }

    public static bool Still(IntPtr h, int spriteW, int spriteH, int x, out Rectangle r)
    {
        return Usable(h, spriteW, spriteH, out r) && TopVisible(h, x, r.Top);
    }

    // En üstteki uygun pencere (EnumWindows ön plandan arkaya sıralar); yoksa Zero.
    // atX verilirse yalnız üst kenarı (atX, nearY) noktasına yakın (±70 px) pencereler: sürükleyip bırakılan yer.
    public static IntPtr Find(int spriteW, int spriteH, out Rectangle rect, int atX = int.MinValue, int nearY = 0)
    {
        uint me = (uint)Process.GetCurrentProcess().Id;
        IntPtr found = IntPtr.Zero;
        Rectangle fr = Rectangle.Empty;
        EnumWindows((h, l) =>
        {
            uint pid;
            GetWindowThreadProcessId(h, out pid);
            if (pid == me || GetWindowTextLength(h) == 0) return true;
            var cls = new StringBuilder(64);
            GetClassName(h, cls, 64);
            if (Skip.Contains(cls.ToString())) return true;
            Rectangle r;
            if (!Usable(h, spriteW, spriteH, out r)) return true;
            if (atX != int.MinValue && (atX < r.Left || atX > r.Right || Math.Abs(r.Top - nearY) > 70)) return true;
            if (!TopVisible(h, atX != int.MinValue ? atX : r.Left + r.Width / 2, r.Top)) return true;
            found = h; fr = r;
            return false;
        }, IntPtr.Zero);
        rect = fr;
        return found;
    }
}

// Çekim için masaüstü klasör sahneleri: simgelerin yeri (Explorer'ın masaüstü görünümü, IFolderView), dekor
// klasörleri kurma/geri alma (gerçekler "gizli" özelliğiyle saklanır, yolları değişmez), sahne sözleri
// (dekor/sahneler.txt) ve açılan Explorer penceresinde dosya seçme (Shell.Application).
static class Desk
{
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }

    [ComImport, Guid("9BA05972-F6A8-11CF-A442-00A0C90A8F39")] class ShellWindowsCls { }

    [ComImport, Guid("85CB6900-4D95-11CF-960C-0080C7F4EE85"), InterfaceType(ComInterfaceType.InterfaceIsDual)]
    interface IShellWindows
    {
        int Count { get; }
        [return: MarshalAs(UnmanagedType.IDispatch)] object Item(object index);
        [return: MarshalAs(UnmanagedType.IUnknown)] object _NewEnum();
        void Register([MarshalAs(UnmanagedType.IDispatch)] object pid, int hwnd, int swClass, out int cookie);
        void RegisterPending(int threadId, ref object loc, ref object root, int swClass, out int cookie);
        void Revoke(int cookie);
        void OnNavigate(int cookie, ref object loc);
        void OnActivated(int cookie, bool active);
        [return: MarshalAs(UnmanagedType.IDispatch)] object FindWindowSW(ref object loc, ref object root, int swClass, out int hwnd, int options);
    }

    [ComImport, Guid("6D5140C1-7436-11CE-8034-00AA006009FA"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IComServiceProvider { [return: MarshalAs(UnmanagedType.IUnknown)] object QueryService(ref Guid sid, ref Guid iid); }

    // yalnız QueryActiveShellView çağrılır; öncekiler sıra tutmak için
    [ComImport, Guid("000214E2-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellBrowser
    {
        void GetWindow(out IntPtr h); void ContextSensitiveHelp(bool f);
        void InsertMenusSB(); void SetMenuSB(); void RemoveMenusSB(); void SetStatusTextSB(); void EnableModelessSB();
        void TranslateAcceleratorSB(); void BrowseObject(); void GetViewStateStream(); void GetControlWindow(); void SendControlMsg();
        [return: MarshalAs(UnmanagedType.IUnknown)] object QueryActiveShellView();
    }

    [ComImport, Guid("CDE725B0-CCC9-4519-917E-325D72FAB4CE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IFolderView
    {
        void GetCurrentViewMode(out uint mode); void SetCurrentViewMode(uint mode);
        void GetFolder(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object ppv);
        void Item(int i, out IntPtr pidl);
        void ItemCount(uint flags, out int n);
        void Items(uint flags, ref Guid iid, out IntPtr ppv);
        void GetSelectionMarkedItem(out int i); void GetFocusedItem(out int i);
        void GetItemPosition(IntPtr pidl, out POINT pt);
        void GetSpacing(out POINT pt); void GetDefaultSpacing(out POINT pt);
        [PreserveSig] int GetAutoArrange();
        void SelectItem(int i, uint flags);
        void SelectAndPositionItems(uint n, [MarshalAs(UnmanagedType.LPArray)] IntPtr[] pidls, [MarshalAs(UnmanagedType.LPArray)] POINT[] pts, uint flags);
    }

    [DllImport("shell32.dll")] static extern int SHGetNameFromIDList(IntPtr pidl, uint sigdn, out IntPtr name);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern void SHChangeNotify(int ev, uint flags, string a, IntPtr b);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
    [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] static extern bool ScreenToClient(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hh, uint flags);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);

    public class Item { public string Name, Path; public Rectangle Rect; }
    public class Line { public string Key, Text, Emote, Clip; public double Secs; }

    public static string DekorDir { get { return Path.Combine(Config.Dir, "dekor"); } }
    static string StateFile { get { return Path.Combine(DekorDir, "kurulum.txt"); } }
    static string ScenesFile { get { return Path.Combine(DekorDir, "sahneler.txt"); } }
    static string Desktop { get { return Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory); } }
    public static bool IsSetUp { get { return File.Exists(StateFile); } }

    // Explorer'ın masaüstü görünümü; list: simgelerin çizildiği pencere (simge yerleri onun istemci koordinatında).
    static IFolderView DesktopView(out IntPtr list)
    {
        var sw = (IShellWindows)new ShellWindowsCls();
        object loc = 0, root = null; // CSIDL_DESKTOP
        int hwnd;
        var disp = sw.FindWindowSW(ref loc, ref root, 8 /* SWC_DESKTOP */, out hwnd, 1 /* SWFO_NEEDDISPATCH */);
        var sid = new Guid("4C96BE40-915C-11CF-99D3-00AA004AE837"); // SID_STopLevelBrowser
        var iid = typeof(IShellBrowser).GUID;
        var browser = (IShellBrowser)((IComServiceProvider)disp).QueryService(ref sid, ref iid);
        var view = (IFolderView)browser.QueryActiveShellView();
        // görünüm başka süreçte: penceresi Progman'ın (duvar kâğıdı slayt gösterisinde bir WorkerW'nin) altında
        IntPtr defView = FindWindowEx(FindWindowEx(IntPtr.Zero, IntPtr.Zero, "Progman", null), IntPtr.Zero, "SHELLDLL_DefView", null);
        for (IntPtr w = IntPtr.Zero; defView == IntPtr.Zero && (w = FindWindowEx(IntPtr.Zero, w, "WorkerW", null)) != IntPtr.Zero; )
            defView = FindWindowEx(w, IntPtr.Zero, "SHELLDLL_DefView", null);
        list = FindWindowEx(defView, IntPtr.Zero, "SysListView32", null);
        if (list == IntPtr.Zero) list = defView;
        return view;
    }

    // Masaüstü kökünün çocuk pidl'i aynı zamanda tam pidl'dir: adı/yolu doğrudan alınır (yolu olmayan: Geri Dönüşüm Kutusu).
    static string NameOf(IntPtr pidl, uint sigdn)
    {
        IntPtr p;
        if (SHGetNameFromIDList(pidl, sigdn, out p) != 0) return null;
        try { return Marshal.PtrToStringUni(p); } finally { Marshal.FreeCoTaskMem(p); }
    }

    const uint SIGDN_FILESYSPATH = 0x80058000;

    // Masaüstündeki görünen simgeler ve ekrandaki hücreleri.
    public static List<Item> Items()
    {
        var res = new List<Item>();
        IntPtr list;
        var fv = DesktopView(out list);
        POINT sp;
        fv.GetSpacing(out sp);
        int n;
        fv.ItemCount(2 /* SVGIO_ALLVIEW */, out n);
        for (int i = 0; i < n; i++)
        {
            IntPtr pidl;
            fv.Item(i, out pidl);
            try
            {
                POINT p;
                fv.GetItemPosition(pidl, out p);
                ClientToScreen(list, ref p);
                res.Add(new Item { Name = NameOf(pidl, 0), Path = NameOf(pidl, SIGDN_FILESYSPATH), Rect = new Rectangle(p.X, p.Y, sp.X, sp.Y) });
            }
            finally { Marshal.FreeCoTaskMem(pidl); }
        }
        return res;
    }

    public static Item Find(string folder)
    {
        return Items().FirstOrDefault(i => i.Path != null && string.Equals(Path.GetFileName(i.Path), folder, StringComparison.OrdinalIgnoreCase));
    }

    // Simgeleri yerlerine taşır (anahtar: tam yol, değer: hücrenin ekrandaki sol üstü). Hücre boyu (spacing) döner.
    static Size Place(Dictionary<string, Point> where)
    {
        IntPtr list;
        var fv = DesktopView(out list);
        POINT sp;
        fv.GetSpacing(out sp);
        int n;
        fv.ItemCount(2, out n);
        for (int i = 0; i < n; i++)
        {
            IntPtr pidl;
            fv.Item(i, out pidl);
            try
            {
                string path = NameOf(pidl, SIGDN_FILESYSPATH);
                Point at;
                if (path == null || !where.TryGetValue(path, out at)) continue;
                var p = new POINT { X = at.X, Y = at.Y };
                ScreenToClient(list, ref p);
                fv.SelectAndPositionItems(1, new[] { pidl }, new[] { p }, 0x80 /* SVSI_POSITIONITEM */);
            }
            finally { Marshal.FreeCoTaskMem(pidl); }
        }
        return new Size(sp.X, sp.Y);
    }

    static void Changed(int what, string path) { SHChangeNotify(what, 0x5 /* SHCNF_PATHW */, path, IntPtr.Zero); }

    // Gizlilikten çıkan/yeni taşınan simgeyi masaüstü biraz geç görür: tek denemede bazen yerine konamıyor, boş bir
    // hücreye düşüyordu (Yeni klasör sağ sütuna kaçtı). Yerleşene kadar (en çok ~8 sn) tekrar dener.
    public static void PlaceSure(Dictionary<string, Point> where)
    {
        where = new Dictionary<string, Point>(where, StringComparer.OrdinalIgnoreCase);
        for (int i = 0; i < 10 && where.Count > 0; i++)
        {
            Thread.Sleep(i == 0 ? 600 : 700);
            try { Place(where); } catch (Exception ex) { Program.LogQuiet("dekor: yerleştirme " + ex.Message); continue; }
            Thread.Sleep(150);
            try
            {
                foreach (var it in Items())
                {
                    Point p;
                    if (it.Path != null && where.TryGetValue(it.Path, out p) && Math.Abs(it.Rect.X - p.X) < 30 && Math.Abs(it.Rect.Y - p.Y) < 30) where.Remove(it.Path);
                }
            }
            catch { }
        }
        if (where.Count > 0) Program.LogQuiet("dekor: yerine konamadı " + string.Join(", ", where.Keys));
    }

    // Çekim masaüstü: masaüstündeki gerçek klasör/dosyalar gizlenir (yolları aynı kalır), dekor/ içindeki klasörler
    // masaüstüne taşınıp sağ üstte bir sütuna dizilir. Yapılanlar kurulum.txt'ye önce yazılır; Restore onu geri alır.
    // bos: dekor klasörler konmaz, masaüstü simgesiz kalır (klasörsüz konuşma sahneleri için).
    public static string Setup(bool bos = false)
    {
        if (IsSetUp) return "Masaüstü zaten çekime hazır~";
        var shown = new List<Item>();
        try { shown = Items(); } catch (Exception ex) { Program.LogQuiet("dekor: simgeler okunamadı " + ex.Message); }
        var state = new List<string>();
        var hide = new List<string>();
        foreach (var p in Directory.GetFileSystemEntries(Desktop))
        {
            var a = File.GetAttributes(p);
            if ((a & (FileAttributes.Hidden | FileAttributes.System)) != 0) continue;
            var it = shown.FirstOrDefault(x => string.Equals(x.Path, p, StringComparison.OrdinalIgnoreCase));
            state.Add("gizli|" + p + "|" + (it != null ? it.Rect.X + "|" + it.Rect.Y : ""));
            hide.Add(p);
        }
        var props = !bos && Directory.Exists(DekorDir) ? Directory.GetDirectories(DekorDir).Where(d => !Directory.Exists(Path.Combine(Desktop, Path.GetFileName(d)))).ToList() : new List<string>();
        foreach (var d in props) state.Add("dekor|" + Path.GetFileName(d));
        Directory.CreateDirectory(DekorDir);
        File.WriteAllLines(StateFile, state, Encoding.UTF8);
        foreach (var p in hide)
        {
            File.SetAttributes(p, File.GetAttributes(p) | FileAttributes.Hidden);
            Changed(0x800 /* SHCNE_ATTRIBUTES */, p);
        }
        var moved = new List<string>();
        foreach (var d in props)
        {
            string to = Path.Combine(Desktop, Path.GetFileName(d));
            Directory.Move(d, to);
            Changed(0x8 /* SHCNE_MKDIR */, to);
            moved.Add(to);
        }
        Changed(0x1000 /* SHCNE_UPDATEDIR */, Desktop);
        // sağda alt alta (Sakura'nın köşesine yakın; üstte 3 hücre boşluk: Sakura simgenin yanında ayağa kalkınca başı
        // ekrandan taşmasın)
        try
        {
            var wa = Screen.PrimaryScreen.WorkingArea;
            var cell = Place(new Dictionary<string, Point>());
            var where = new Dictionary<string, Point>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < moved.Count; i++) where[moved[i]] = new Point(wa.Right - cell.Width - 12, wa.Top + 12 + (i + 3) * cell.Height);
            PlaceSure(where);
        }
        catch (Exception ex) { Program.LogQuiet("dekor: yerleştirilemedi " + ex.Message); }
        return "Masaüstü çekime hazır! " + hide.Count + " şeyi sakladım, " + moved.Count + " dekor klasör koydum~";
    }

    // Kurulumu geri alır: dekorlar dekor/ klasörüne döner, gizlenenler görünür olur ve eski yerlerine konur.
    public static string Restore()
    {
        if (!IsSetUp) return "Masaüstü zaten normal~";
        var where = new Dictionary<string, Point>(StringComparer.OrdinalIgnoreCase);
        foreach (var line in File.ReadAllLines(StateFile, Encoding.UTF8))
        {
            var f = line.Split('|');
            if (f[0] == "dekor" && f.Length > 1)
            {
                string on = Path.Combine(Desktop, f[1]), back = Path.Combine(DekorDir, f[1]);
                if (Directory.Exists(on) && !Directory.Exists(back)) { Directory.Move(on, back); Changed(0x10 /* SHCNE_RMDIR */, on); }
            }
            else if (f[0] == "gizli" && f.Length > 1 && (File.Exists(f[1]) || Directory.Exists(f[1])))
            {
                File.SetAttributes(f[1], File.GetAttributes(f[1]) & ~FileAttributes.Hidden);
                Changed(0x800, f[1]);
                int x, y;
                if (f.Length > 3 && int.TryParse(f[2], out x) && int.TryParse(f[3], out y)) where[f[1]] = new Point(x, y);
            }
        }
        Changed(0x1000, Desktop);
        PlaceSure(where);
        File.Delete(StateFile);
        return "Masaüstü eski haline döndü~";
    }

    // dekor/sahneler.txt: [Klasör adı] başlıkları, altında "anahtar = söz | ifade" (# ile başlayan satır yorum).
    // Anahtarlar: giris (simgenin yanında), acinca (pencereye oturunca), dosya adları (sırayla), cikis (en son).
    public static List<KeyValuePair<string, List<Line>>> Scenes()
    {
        var res = new List<KeyValuePair<string, List<Line>>>();
        if (!File.Exists(ScenesFile)) return res;
        List<Line> cur = null;
        foreach (var raw in File.ReadAllLines(ScenesFile, Encoding.UTF8))
        {
            var s = raw.Trim();
            if (s.Length == 0 || s.StartsWith("#")) continue;
            if (s.StartsWith("[") && s.EndsWith("]")) { cur = new List<Line>(); res.Add(new KeyValuePair<string, List<Line>>(s.Substring(1, s.Length - 2).Trim(), cur)); continue; }
            int eq = s.IndexOf('=');
            if (cur == null || eq < 0) continue;
            var parts = s.Substring(eq + 1).Split('|');
            string text = parts[0], emote = parts.Length > 1 ? parts[1].Trim() : "mutlu";
            double secs = 0;
            if (parts.Length > 2) double.TryParse(parts[2].Trim().Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out secs);
            cur.Add(new Line { Key = s.Substring(0, eq).Trim(), Text = text.Trim(), Emote = Emotes.Keys.Contains(emote) ? emote : "mutlu", Secs = secs, Clip = parts.Length > 3 ? parts[3].Trim() : null });
        }
        return res;
    }

    public static List<Line> SceneLines(string folder)
    {
        var sc = Scenes().FirstOrDefault(k => string.Equals(k.Key, folder, StringComparison.OrdinalIgnoreCase));
        return sc.Value ?? new List<Line>();
    }

    static object Call(object o, string name, params object[] args) { return o.GetType().InvokeMember(name, System.Reflection.BindingFlags.InvokeMethod, null, o, args); }
    static object Get(object o, string name) { return o.GetType().InvokeMember(name, System.Reflection.BindingFlags.GetProperty, null, o, null); }

    // Bu klasörü gösteren Explorer penceresi (sekmede açıldıysa sekmenin penceresi); doc: dosya seçmek için sekmenin görünümü.
    public static IntPtr FindExplorer(string path, out object doc)
    {
        doc = null;
        try
        {
            var shell = Activator.CreateInstance(Type.GetTypeFromProgID("Shell.Application"));
            var wins = Call(shell, "Windows");
            int n = Convert.ToInt32(Get(wins, "Count"));
            for (int i = 0; i < n; i++)
            {
                try
                {
                    var w = Call(wins, "Item", i);
                    if (w == null) continue;
                    var d = Get(w, "Document");
                    var p = (string)Get(Get(Get(d, "Folder"), "Self"), "Path");
                    if (!string.Equals(p.TrimEnd('\\'), path.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) continue;
                    doc = d;
                    return new IntPtr(Convert.ToInt64(Get(w, "HWND")));
                }
                catch { }
            }
        }
        catch (Exception ex) { Program.LogQuiet("sahne: pencere aranamadı " + ex.Message); }
        return IntPtr.Zero;
    }

    [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);

    // Medya tuşu (Spotify ve diğer çalarlar dinler): 0xB0 sonraki, 0xB3 oynat/duraklat.
    public static void MediaKey(byte vk) { keybd_event(vk, 0, 0, IntPtr.Zero); keybd_event(vk, 0, 2, IntPtr.Zero); }

    // Spotify penceresini simge durumundan çıkarıp verilen yere koyar (müzik sahnesinde kadrajda görünsün).
    public static bool ShowSpotify(Rectangle r)
    {
        foreach (var p in Process.GetProcessesByName("Spotify"))
        {
            IntPtr h;
            try { h = p.MainWindowHandle; } catch { continue; }
            if (h == IntPtr.Zero) continue;
            ShowWindow(h, 9 /* SW_RESTORE */);
            PlaceWindow(h, r);
            return true;
        }
        return false;
    }

    // Klasörü gösteren Explorer penceresini (sekmede açıldıysa yalnız o sekmeyi) kapatır.
    public static void CloseFolder(string path)
    {
        try
        {
            var shell = Activator.CreateInstance(Type.GetTypeFromProgID("Shell.Application"));
            var wins = Call(shell, "Windows");
            int n = Convert.ToInt32(Get(wins, "Count"));
            for (int i = n - 1; i >= 0; i--)
            {
                try
                {
                    var w = Call(wins, "Item", i);
                    var p = (string)Get(Get(Get(Get(w, "Document"), "Folder"), "Self"), "Path");
                    if (string.Equals(p.TrimEnd('\\'), path.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) Call(w, "Quit");
                }
                catch { }
            }
        }
        catch (Exception ex) { Program.LogQuiet("sahne: kapatılamadı " + ex.Message); }
    }

    // Explorer'da dosyayı seçili ve görünür yapar (Sakura ondan bahsederken).
    public static void Select(object doc, string file)
    {
        if (doc == null) return;
        try
        {
            var fi = Call(Get(doc, "Folder"), "ParseName", file);
            if (fi != null) Call(doc, "SelectItem", fi, 1 | 4 | 8 | 16); // seç, diğerlerini bırak, görünür yap, odakla
        }
        catch { }
    }

    public static void PlaceWindow(IntPtr h, Rectangle r)
    {
        if (IsZoomed(h)) ShowWindow(h, 9 /* SW_RESTORE */);
        // arka planda açılmış olabilir (Sakura ön planda değil, odak çalamaz): bir anlığına en üste alıp bırakınca öne gelir
        SetWindowPos(h, new IntPtr(-1) /* HWND_TOPMOST */, r.X, r.Y, r.Width, r.Height, 0x10 /* SWP_NOACTIVATE */);
        SetWindowPos(h, new IntPtr(-2) /* HWND_NOTOPMOST */, 0, 0, 0, 0, 0x1 | 0x2 | 0x10 /* NOSIZE | NOMOVE | NOACTIVATE */);
    }

    // Test: masaüstündeki simgeler ve yerleri
    public static string Dump()
    {
        var sb = new StringBuilder();
        sb.AppendLine("ekran " + Screen.PrimaryScreen.Bounds + " çalışma " + Screen.PrimaryScreen.WorkingArea);
        foreach (var i in Items()) sb.AppendLine(i.Name + " | " + i.Path + " | " + i.Rect);
        return sb.ToString();
    }
}

static class Activity
{
    [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO info);

    // Son klavye/fare girdisinin TickCount zamanı. Hangi tuş olduğu okunmaz.
    public static uint LastInputTick()
    {
        var li = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO)) };
        return GetLastInputInfo(ref li) ? li.dwTime : 0;
    }

    public static double IdleSeconds()
    {
        var li = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO)) };
        if (!GetLastInputInfo(ref li)) return 0;
        return ((uint)Environment.TickCount - li.dwTime) / 1000.0;
    }
}

// Sabah hava durumu: Open-Meteo (anahtarsız, ücretsiz). Şehir bir kez koordinata çevrilip config'te saklanır.
static class Weather
{
    static readonly Dictionary<int, string> Codes = new Dictionary<int, string> {
        { 0, "açık" }, { 1, "çoğunlukla açık" }, { 2, "parçalı bulutlu" }, { 3, "kapalı" }, { 45, "sisli" }, { 48, "sisli" },
        { 51, "çiseliyor" }, { 53, "çiseliyor" }, { 55, "çiseliyor" }, { 56, "dondurucu çisenti" }, { 57, "dondurucu çisenti" },
        { 61, "yağmurlu" }, { 63, "yağmurlu" }, { 65, "kuvvetli yağmur" }, { 66, "dondurucu yağmur" }, { 67, "dondurucu yağmur" },
        { 71, "karlı" }, { 73, "karlı" }, { 75, "yoğun kar" }, { 77, "kar taneleri" }, { 80, "sağanak" }, { 81, "sağanak" },
        { 82, "kuvvetli sağanak" }, { 85, "kar sağanağı" }, { 86, "kar sağanağı" }, { 95, "gök gürültülü fırtına" },
        { 96, "dolulu fırtına" }, { 99, "dolulu fırtına" },
    };

    static Dictionary<string, object> Get(string url)
    {
        System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
        using (var wc = new System.Net.WebClient { Encoding = Encoding.UTF8 })
            return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(wc.DownloadString(url));
    }

    static double Num(object o) { return Convert.ToDouble(o, CultureInfo.InvariantCulture); }

    // Hava efekti için anlık durum: {kod, sıcaklık}; hata olursa null.
    public static int[] Current(Config cfg)
    {
        try
        {
            if (!Coords(cfg)) return null;
            var w = Get("https://api.open-meteo.com/v1/forecast?latitude=" + cfg.CityLat + "&longitude=" + cfg.CityLon + "&current=temperature_2m,weather_code&timezone=auto");
            var cur = (Dictionary<string, object>)w["current"];
            return new[] { (int)Num(cur["weather_code"]), (int)Math.Round(Num(cur["temperature_2m"])) };
        }
        catch { return null; }
    }

    // Kod ve sıcaklıktan efekt: "rain", "snow", "hot" ya da "".
    public static string Fx(int code, int temp)
    {
        if (code >= 71 && code <= 77 || code == 85 || code == 86) return "snow";
        if (code >= 51 && code <= 67 || code >= 80 && code <= 82 || code >= 95) return "rain";
        return temp >= 32 ? "hot" : "";
    }

    static bool Coords(Config cfg)
    {
        if (cfg.CityLat != "" && cfg.CityLon != "") return true;
        if (cfg.City == "") return false;
        var geo = Get("https://geocoding-api.open-meteo.com/v1/search?count=1&language=tr&name=" + Uri.EscapeDataString(cfg.City));
        var res = geo.ContainsKey("results") ? geo["results"] as System.Collections.ArrayList : null;
        if (res == null || res.Count == 0) return false;
        var r = (Dictionary<string, object>)res[0];
        string lat = Num(r["latitude"]).ToString(CultureInfo.InvariantCulture), lon = Num(r["longitude"]).ToString(CultureInfo.InvariantCulture);
        cfg.CityLat = lat;
        cfg.CityLon = lon;
        Config.Patch(c => { c.CityLat = lat; c.CityLon = lon; });
        return true;
    }

    public static Event Morning(Config cfg)
    {
        try
        {
            if (cfg.CityLat == "" || cfg.CityLon == "")
            {
                var geo = Get("https://geocoding-api.open-meteo.com/v1/search?count=1&language=tr&name=" + Uri.EscapeDataString(cfg.City));
                var res = geo.ContainsKey("results") ? geo["results"] as System.Collections.ArrayList : null;
                if (res == null || res.Count == 0) return null;
                var r = (Dictionary<string, object>)res[0];
                string lat = Num(r["latitude"]).ToString(CultureInfo.InvariantCulture), lon = Num(r["longitude"]).ToString(CultureInfo.InvariantCulture);
                cfg.CityLat = lat;
                cfg.CityLon = lon;
                Config.Patch(c => { c.CityLat = lat; c.CityLon = lon; });
            }
            var w = Get("https://api.open-meteo.com/v1/forecast?latitude=" + cfg.CityLat + "&longitude=" + cfg.CityLon +
                        "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=1");
            var cur = (Dictionary<string, object>)w["current"];
            var daily = (Dictionary<string, object>)w["daily"];
            int code = (int)Num(cur["weather_code"]);
            int temp = (int)Math.Round(Num(cur["temperature_2m"]));
            int hi = (int)Math.Round(Num(((System.Collections.ArrayList)daily["temperature_2m_max"])[0]));
            int lo = (int)Math.Round(Num(((System.Collections.ArrayList)daily["temperature_2m_min"])[0]));
            string desc;
            if (!Codes.TryGetValue(code, out desc)) desc = "";
            bool wet = code >= 51 && code <= 82 || code >= 95;
            return new Event
            {
                Mode = "weather", Title = "Günaydın!", Click = null, Prefix = "wave_",
                Body = string.Format("{0}: {1}°C, {2}", cfg.City, temp, desc),
                Footer = wet ? "Şemsiyeni unutma!" : string.Format("Gün içinde {0}° / {1}°", lo, hi),
                Emote = wet ? "saskin" : "mutlu",
            };
        }
        catch { return null; }
    }
}

// Claude Code komutları ve hook'ları bir Windows "iş nesnesi" (job) içinde çalışır; Claude oturumu kapanınca ya da
// yenilenince içindeki bütün süreçler de kapanır. Uzun yaşayan süreçler (masaüstü arkadaşı, mesaj izleyicisi) bu
// yüzden WMI ile başlatılır: üst süreçleri WmiPrvSE olur ve Claude'dan bağımsız yaşarlar.
static class Detached
{
    [DllImport("kernel32.dll")] static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string title);

    public static bool InJob()
    {
        bool r;
        return IsProcessInJob(GetCurrentProcess(), IntPtr.Zero, out r) && r;
    }

    public static void Start(string exe, string args)
    {
        try
        {
            using (var cls = new System.Management.ManagementClass("Win32_Process"))
            {
                var inp = cls.GetMethodParameters("Create");
                inp["CommandLine"] = "\"" + exe + "\" " + args;
                inp["CurrentDirectory"] = Config.Dir;
                cls.InvokeMethod("Create", inp, null);
            }
        }
        catch { Process.Start(new ProcessStartInfo(exe, args) { UseShellExecute = false, WorkingDirectory = Config.Dir }); }
    }

    // Her bildirimde çağrılır: kapanmış olan ana programı (tepsi, mesaj izleyici, arkadaş) sessizce yeniden başlatır.
    public static void EnsureRunning(Config cfg)
    {
        if (!PetForm.IsRunning()) Start(Application.ExecutablePath, "host --detached");
    }
}

// Sakura'nın Windows açılışında başlaması için Başlangıç klasörü kısayolu.
static class Startup
{
    static string LinkPath { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), "Sakura.lnk"); } }

    public static void Add() { Installer.Shortcut(LinkPath, "", "Sakura masaüstü arkadaşı"); }

    public static void Remove() { try { if (File.Exists(LinkPath)) File.Delete(LinkPath); } catch { } }
}

// Görünüm penceresi: görünüm/ifade seçimi, grup renkleri, ses, süre, boyut, arkadaş modu ve rahatsız etmeme.
class SettingsForm : Form
{
    static readonly string[,] Presets = {
        { "Orijinal", "" }, { "Pembe", "#f58fb8" }, { "Kırmızı", "#d63a4a" }, { "Kızıl", "#e0662e" },
        { "Sarı", "#f2c94c" }, { "Nane", "#5fd4c0" }, { "Yeşil", "#4caf6a" }, { "Mavi", "#5b8def" },
        { "Lacivert", "#2b3a7a" }, { "Mor", "#9a7ae6" }, { "Kahve", "#8a5a3a" }, { "Siyah", "#2e2a3a" },
        { "Gümüş", "#d8dce8" }, { "Beyaz", "#f4f4f8" },
    };
    static readonly string[] GroupNames = { "Saç", "Gözler", "Kıyafet", "Kurdele / aksesuar" };

    readonly Config cfg;
    readonly string part;
    readonly PetForm host;
    readonly PictureBox preview = new PictureBox();
    readonly System.Windows.Forms.Timer anim = new System.Windows.Forms.Timer();
    readonly Dictionary<string, Label> current = new Dictionary<string, Label>();
    readonly Dictionary<string, Sprites> sprites = new Dictionary<string, Sprites>();
    List<Bitmap> frames = new List<Bitmap>();
    int frame, previewEmote;

    public SettingsForm(Config cfg, string part, PetForm host)
    {
        this.cfg = cfg;
        this.part = part;
        this.host = host;
        Text = "Sakura — Görünüm";
        Font = new Font("Segoe UI", 9.5f);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(32, 30, 40);
        ForeColor = Color.FromArgb(235, 232, 240);
        ClientSize = part == "look" ? new Size(760, 420) : new Size(760, 600);
        var exeIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if (exeIcon != null) Icon = exeIcon;

        if (part == "look")
        {
            var stage = new Panel { Left = 16, Top = 16, Width = 224, Height = 288, BackColor = Color.FromArgb(48, 46, 60) };
            preview.Dock = DockStyle.Fill;
            preview.Paint += (s, e) =>
            {
                if (frames.Count == 0) return;
                e.Graphics.InterpolationMode = InterpolationMode.NearestNeighbor;
                e.Graphics.PixelOffsetMode = PixelOffsetMode.Half;
                var f = frames[frame];
                e.Graphics.DrawImage(f, (stage.Width - f.Width) / 2, (stage.Height - f.Height) / 2, f.Width, f.Height);
            };
            stage.Controls.Add(preview);
            Controls.Add(stage);

            int x0 = 260, y = 16;
            Controls.Add(new Label { Text = "Görünüm", Left = x0, Top = y + 4, AutoSize = true });
            var look = new ComboBox { Left = x0 + 130, Top = y, Width = 200, DropDownStyle = ComboBoxStyle.DropDownList };
            var lookNames = Config.Looks();
            look.Items.AddRange(lookNames.Select(LookLabel).ToArray());
            int li = Array.IndexOf(lookNames, cfg.Look);
            look.SelectedIndex = li >= 0 ? li : (lookNames.Length > 0 ? 0 : -1);
            look.SelectedIndexChanged += (s, e) => { cfg.Look = lookNames[look.SelectedIndex]; Reload(); };
            Controls.Add(look);
            Controls.Add(new Label { Text = "İfade", Left = x0 + 345, Top = y + 4, AutoSize = true });
            var emote = new ComboBox { Left = x0 + 390, Top = y, Width = 104, DropDownStyle = ComboBoxStyle.DropDownList };
            emote.Items.Add("Rastgele");
            emote.Items.AddRange(Emotes.Labels);
            emote.SelectedIndex = Array.IndexOf(Emotes.Keys, cfg.Emote) + 1;
            emote.SelectedIndexChanged += (s, e) =>
            {
                cfg.Emote = emote.SelectedIndex == 0 ? "rastgele" : Emotes.Keys[emote.SelectedIndex - 1];
                previewEmote = 0;
                RenderPreview();
            };
            Controls.Add(emote);
            y += 40;

            for (int gi = 0; gi < 4; gi++)
            {
                string key = Config.GroupKeys[gi];
                Controls.Add(new Label { Text = GroupNames[gi], Left = x0, Top = y, AutoSize = true, Font = new Font(Font, FontStyle.Bold) });
                var cur = new Label { Left = x0 + 175, Top = y, AutoSize = true, ForeColor = Color.FromArgb(170, 165, 185) };
                current[key] = cur;
                Controls.Add(cur);
                y += 22;
                for (int p = 0; p < Presets.GetLength(0); p++)
                {
                    string name = Presets[p, 0], hex = Presets[p, 1];
                    var b = new Button
                    {
                        Left = x0 + p * 33, Top = y, Width = 28, Height = 28, FlatStyle = FlatStyle.Flat,
                        BackColor = hex == "" ? Color.FromArgb(48, 46, 60) : ColorTranslator.FromHtml(hex),
                        Text = hex == "" ? "↺" : "", ForeColor = Color.White,
                    };
                    b.FlatAppearance.BorderColor = Color.FromArgb(90, 86, 104);
                    new ToolTip().SetToolTip(b, name);
                    b.Click += (s, e) => SetColor(key, hex);
                    Controls.Add(b);
                }
                // Özel renk: grubun yanındaki "özel renk seç" yazısına tıklanınca renk seçici açılır.
                cur.Cursor = Cursors.Hand;
                cur.Click += (s, e) =>
                {
                    using (var dlg = new ColorDialog { FullOpen = true })
                        if (dlg.ShowDialog(this) == DialogResult.OK) SetColor(key, ColorTranslator.ToHtml(Color.FromArgb(dlg.Color.R, dlg.Color.G, dlg.Color.B)).ToLower());
                };
                y += 40;
            }
            Controls.Add(new Label
            {
                Text = "Renk adının yanındaki yazıya tıklayarak özel renk seçebilirsin.",
                Left = 16, Top = 316, Width = 230, Height = 60, ForeColor = Color.FromArgb(170, 165, 185),
            });
        }
        else
        {
            int x0 = 24, y = 16;
            Controls.Add(Header("Genel", x0, y));
            y += 30;
            Controls.Add(new Label { Text = "Balon süresi (sn)", Left = x0, Top = y + 2, AutoSize = true });
            var secs = new NumericUpDown { Left = x0 + 200, Top = y, Width = 50, Minimum = 2, Maximum = 30, Value = (decimal)Math.Max(2, Math.Min(30, cfg.Seconds)) };
            secs.ValueChanged += (s, e) => cfg.Seconds = (double)secs.Value;
            Controls.Add(secs);
            Controls.Add(new Label { Text = "Boyut", Left = x0 + 330, Top = y + 2, AutoSize = true });
            var scale = new ComboBox { Left = x0 + 400, Top = y, Width = 60, DropDownStyle = ComboBoxStyle.DropDownList };
            scale.Items.AddRange(new object[] { "1x", "2x" });
            scale.SelectedIndex = cfg.Scale >= 2 ? 1 : 0;
            scale.SelectedIndexChanged += (s, e) => cfg.Scale = scale.SelectedIndex + 1;
            Controls.Add(scale);
            y += 36;

            var games = new CheckBox { Text = "Tam ekran oyunda gizlen", Left = x0, Top = y, AutoSize = true, Checked = cfg.HideInGames };
            games.CheckedChanged += (s, e) => cfg.HideInGames = games.Checked;
            var full = new CheckBox { Text = "Tam ekran videoda da gizlen", Left = x0 + 330, Top = y, AutoSize = true, Checked = cfg.HideInFullscreen };
            full.CheckedChanged += (s, e) => cfg.HideInFullscreen = full.Checked;
            Controls.Add(games);
            Controls.Add(full);
            y += 32;
            var spotify = new CheckBox { Text = "Spotify'a eşlik etsin", Left = x0, Top = y, AutoSize = true, Checked = cfg.Spotify };
            spotify.CheckedChanged += (s, e) => cfg.Spotify = spotify.Checked;
            Controls.Add(spotify);
            Controls.Add(new Label { Text = "Mola hatırlat (dk, 0 = kapalı)", Left = x0 + 330, Top = y + 2, AutoSize = true });
            var brk = new NumericUpDown { Left = x0 + 560, Top = y, Width = 60, Minimum = 0, Maximum = 240, Value = Math.Max(0, Math.Min(240, cfg.BreakMinutes)) };
            brk.ValueChanged += (s, e) => cfg.BreakMinutes = (int)brk.Value;
            Controls.Add(brk);
            y += 32;
            Controls.Add(new Label { Text = "Şehir (sabah hava durumu)", Left = x0, Top = y + 3, AutoSize = true });
            var city = new TextBox { Left = x0 + 200, Top = y, Width = 160, Text = cfg.City };
            city.TextChanged += (s, e) => { cfg.City = city.Text.Trim(); cfg.CityLat = cfg.CityLon = ""; };
            Controls.Add(city);
            y += 32;
            var screen = new CheckBox { Text = "Ekran farkındalığı (YouTube, Spotify, uygulamalar)", Left = x0, Top = y, AutoSize = true, Checked = cfg.ScreenAware };
            screen.CheckedChanged += (s, e) => cfg.ScreenAware = screen.Checked;
            Controls.Add(screen);
            var sys = new CheckBox { Text = "Sistem uyarıları", Left = x0 + 440, Top = y, AutoSize = true, Checked = cfg.SystemAlerts };
            sys.CheckedChanged += (s, e) => cfg.SystemAlerts = sys.Checked;
            Controls.Add(sys);
            y += 32;
            y += 10;
            Controls.Add(Header("Yapay zekâ", x0, y));
            y += 30;
            var ai = new CheckBox { Text = "Yapay zekâ yorumları", Left = x0, Top = y, AutoSize = true, Checked = cfg.AiComments };
            ai.CheckedChanged += (s, e) => cfg.AiComments = ai.Checked;
            Controls.Add(ai);
            Controls.Add(new Label { Text = "Model", Left = x0 + 330, Top = y + 3, AutoSize = true });
            var model = new ComboBox { Left = x0 + 400, Top = y, Width = 260, DropDownStyle = ComboBoxStyle.DropDownList };
            model.Items.AddRange(new object[] { "Claude Opus 5.5 (varsayılan)", "Claude Haiku 5.5 (daha ucuz)" });
            model.SelectedIndex = cfg.AiModel.StartsWith("claude-haiku") ? 1 : 0;
            model.SelectedIndexChanged += (s, e) => cfg.AiModel = model.SelectedIndex == 1 ? "claude-haiku-5-5" : "claude-opus-5-5";
            Controls.Add(model);
            y += 32;
            Controls.Add(new Label { Text = "Bağlantı", Left = x0, Top = y + 3, AutoSize = true });
            var backend = new ComboBox { Left = x0 + 200, Top = y, Width = 270, DropDownStyle = ComboBoxStyle.DropDownList };
            backend.Items.AddRange(new object[] { "Claude aboneliği (Claude Code)", "API anahtarı" });
            backend.SelectedIndex = cfg.AiBackend == "api" ? 1 : 0;
            backend.SelectedIndexChanged += (s, e) => cfg.AiBackend = backend.SelectedIndex == 1 ? "api" : "max";
            Controls.Add(backend);
            y += 32;
            Controls.Add(new Label { Text = "Claude API anahtarı", Left = x0, Top = y + 3, AutoSize = true });
            var keyBox = new TextBox { Left = x0 + 200, Top = y, Width = 220, UseSystemPasswordChar = true };
            var keyState = new Label { Left = x0 + 430, Top = y + 3, AutoSize = true, ForeColor = Color.FromArgb(170, 165, 185), Text = ApiKey.Has() ? "kayıtlı" : "yok" };
            keyBox.TextChanged += (s, e) => newApiKey = keyBox.Text;
            Controls.Add(keyBox);
            Controls.Add(keyState);
            y += 42;
            Controls.Add(Header("Telefon", x0, y));
            y += 30;
            var phone = new CheckBox { Text = "Telefona bildirim gönder (ntfy uygulaması)", Left = x0, Top = y, AutoSize = true, Checked = cfg.PhoneOn };
            phone.CheckedChanged += (s, e) => cfg.PhoneOn = phone.Checked;
            Controls.Add(phone);
            y += 32;
            Controls.Add(new Label { Text = "ntfy konusu", Left = x0, Top = y + 3, AutoSize = true });
            var topic = new TextBox { Left = x0 + 200, Top = y, Width = 200, ReadOnly = true, Text = Phone.Topic(cfg) };
            var copy = new Button { Text = "Kopyala", Left = x0 + 408, Top = y - 1, Width = 72, Height = 28, FlatStyle = FlatStyle.Flat };
            copy.Click += (s, e) => { try { Clipboard.SetText(topic.Text); copy.Text = "Kopyalandı"; } catch { } };
            Controls.Add(topic);
            Controls.Add(copy);
            y += 32;
            var away = new CheckBox { Text = "Sadece bilgisayar başında değilken (5 dk)", Left = x0, Top = y, AutoSize = true, Checked = cfg.PhoneOnlyAway };
            away.CheckedChanged += (s, e) => cfg.PhoneOnlyAway = away.Checked;
            var ptest = new Button { Text = "Test gönder", Left = x0 + 330, Top = y - 2, Width = 100, Height = 28, FlatStyle = FlatStyle.Flat };
            var pstate = new Label { Left = x0 + 438, Top = y + 3, AutoSize = true, ForeColor = Color.FromArgb(170, 165, 185) };
            ptest.Click += (s, e) =>
            {
                pstate.Text = "…";
                string topicName = topic.Text;
                Task.Run(() => Phone.Post(topicName, "Sakura", "Merhaba~ Telefona bildirimler böyle gelecek!", "cherry_blossom"))
                    .ContinueWith(r => BeginInvoke((Action)(() => pstate.Text = r.Result == null ? "gönderildi ✓" : "hata")));
            };
            Controls.Add(away);
            Controls.Add(ptest);
            Controls.Add(pstate);
        }

        var saved = new Label { Left = ClientSize.Width - 380, Top = ClientSize.Height - 41, Width = 140, TextAlign = ContentAlignment.MiddleRight, ForeColor = Color.FromArgb(170, 165, 185) };
        var save = new Button { Text = "Kaydet", Left = ClientSize.Width - 252, Top = ClientSize.Height - 48, Width = 90, Height = 32, FlatStyle = FlatStyle.Flat };
        save.Click += (s, e) => { Apply(); saved.Text = "Kaydedildi ✓"; };
        Controls.AddRange(new Control[] { saved, save });
        if (part == "look")
        {
            var test = new Button { Text = "Kaydet ve dene", Left = ClientSize.Width - 152, Top = ClientSize.Height - 48, Width = 140, Height = 32, FlatStyle = FlatStyle.Flat };
            test.Click += (s, e) =>
            {
                Apply();
                saved.Text = "Kaydedildi ✓";
                host.Preview(new Event { Title = "Deneme", Body = "Böyle görüneceğim!", Footer = "Görünüm kaydedildi", Emote = Emotes.Pick("done", cfg) });
            };
            Controls.Add(test);
        }
        else save.Left = ClientSize.Width - 112;
        if (part != "look") return;

        anim.Interval = 90;
        anim.Tick += (s, e) =>
        {
            if (frames.Count == 0) return;
            frame = (frame + 1) % frames.Count;
            // "Rastgele" seçiliyse önizleme her turda bir sonraki ifadeye geçer.
            if (frame == 0 && !Emotes.Keys.Contains(cfg.Emote)) { previewEmote = (previewEmote + 1) % Emotes.Keys.Length; RenderPreview(); }
            preview.Invalidate();
        };
        Reload();
        anim.Start();
    }

    string newApiKey = "";

    static Label Header(string text, int x, int y)
    {
        return new Label { Text = text, Left = x, Top = y, AutoSize = true, Font = new Font("Segoe UI", 11f, FontStyle.Bold), ForeColor = Color.FromArgb(240, 140, 180) };
    }

    // Yalnızca bu sayfanın alanlarını kaydeder (öbür sayfa ve hızlı ayarlar ezilmesin), ana program anında uygular.
    void Apply()
    {
        if (newApiKey.Trim() != "") ApiKey.Set(newApiKey); // anahtar düz metin olarak config'e yazılmaz, şifreli saklanır
        var d = cfg;
        if (part == "look")
            Config.Patch(c => { c.Look = d.Look; c.Emote = d.Emote; c.Colors = new Dictionary<string, string>(d.Colors); });
        else
            Config.Patch(c =>
            {
                c.Seconds = d.Seconds; c.Scale = d.Scale; c.HideInGames = d.HideInGames; c.HideInFullscreen = d.HideInFullscreen;
                c.Spotify = d.Spotify; c.BreakMinutes = d.BreakMinutes; c.ScreenAware = d.ScreenAware; c.SystemAlerts = d.SystemAlerts;
                c.AiComments = d.AiComments; c.AiModel = d.AiModel; c.AiBackend = d.AiBackend;
                c.PhoneOn = d.PhoneOn; c.PhoneOnlyAway = d.PhoneOnlyAway; c.NtfyTopic = d.NtfyTopic;
                if (c.City != d.City) { c.City = d.City; c.CityLat = c.CityLon = ""; }
            });
        host.ReloadSettings();
    }

    static string LookLabel(string name)
    {
        switch (name)
        {
            case "yeni": return "Sakura (yeni çizim)";
            case "yeni-gozluk": return "Sakura + gözlük";
            case "yeni-kulaklik": return "Sakura + kulaklık";
            case "yeni-kedi": return "Sakura + kedi kulağı";
            case "yeni-bere": return "Sakura + bayrak beresi";
            case "klasik": return "Klasik (bluz, hırka)";
            case "gamer": return "Gamer (kapüşonlu, kulaklık)";
            case "gotik": return "Gotik kedi";
            case "festival": return "Festival (yukata)";
            case "tilki": return "Tilki (kimono)";
            default: return name;
        }
    }

    void SetColor(string key, string hex)
    {
        cfg.Colors[key] = hex;
        RenderPreview();
    }

    void Reload()
    {
        sprites.Clear();
        RenderPreview();
    }

    void RenderPreview()
    {
        foreach (var f in frames) f.Dispose();
        string em = Emotes.Keys.Contains(cfg.Emote) ? cfg.Emote : Emotes.Keys[previewEmote];
        if (!sprites.ContainsKey(em)) sprites[em] = new Sprites(cfg.Look, "wave_", em);
        frames = sprites[em].Render(cfg.Colors);
        frame = 0;
        foreach (var kv in current)
        {
            var hex = cfg.Colors[kv.Key];
            string name = "Orijinal";
            for (int p = 0; p < Presets.GetLength(0); p++) if (Presets[p, 1] == hex) name = Presets[p, 0];
            if (hex != "" && name == "Orijinal") name = "Özel " + hex;
            kv.Value.Text = name + "  ·  özel renk seç";
        }
        preview.Invalidate();
    }
}

// Stüdyo: Sakura'nın sosyal medyadaki hâli Luna (@luna.pixel) için paylaşım önerileri ve dikey video.
// Öneriler studio\oneriler.json'da, videolar Videolar\Luna klasöründe. Alan adları JSON'la aynı (küçük harf).
class Scene
{
    public string title { get; set; }
    public string text { get; set; }
    public string footer { get; set; }
    public string emote { get; set; }
    public bool wave { get; set; }
    public string look { get; set; }
    public string action { get; set; }
    public string camera { get; set; }
    public string pose { get; set; }
    public Dictionary<string, string> colors { get; set; }
}

class Post
{
    public string day { get; set; }
    public string type { get; set; }
    public string title { get; set; }
    public string idea { get; set; }
    public string music { get; set; }
    public List<Scene> scenes { get; set; }
    public string ig { get; set; }
    public string tiktok { get; set; }
    public string yt_title { get; set; }
    public string yt { get; set; }
    public List<string> hashtags { get; set; }
    public string video { get; set; }
    public string created { get; set; }

    public string Tags() { return hashtags == null ? "" : string.Join(" ", hashtags); }
}

class PostBatch { public List<Post> posts { get; set; } }

static class Studio
{
    public const string Handle = "@luna.pixel";
    static readonly CultureInfo Tr = new CultureInfo("tr-TR");
    static string FilePath { get { return Path.Combine(Config.Dir, "studio", "oneriler.json"); } }

    public static string VideoDir
    {
        get
        {
            string d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyVideos), "Luna");
            Directory.CreateDirectory(d);
            return d;
        }
    }

    public static List<Post> Load()
    {
        try
        {
            if (!File.Exists(FilePath)) return new List<Post>();
            var b = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<PostBatch>(File.ReadAllText(FilePath, Encoding.UTF8));
            return b == null || b.posts == null ? new List<Post>() : b.posts;
        }
        catch (Exception ex) { Program.LogError(ex); return new List<Post>(); }
    }

    public static void Save(List<Post> posts)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath));
            File.WriteAllText(FilePath, new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Serialize(new PostBatch { posts = posts.Take(30).ToList() }), Encoding.UTF8);
        }
        catch (Exception ex) { Program.LogError(ex); }
    }

    const string Instructions =
        "GÖREV: Sosyal medya hesabın " + Handle + " (Instagram Reels, TikTok, YouTube Shorts) için önümüzdeki 3 günün paylaşım önerilerini yazıyorsun: her gün için bir video. " +
        "Videolar senin pixel art karelerinden ve konuşma balonlarından oluşur; seslendirme yok, müziği ev arkadaşın ekler. " +
        "Her video 3-6 sahne. Her sahnede tek bir konuşma balonu olur: balon metni en çok 110 karakter, tek bir düşünce, yüksek sesle söylenecek gibi doğal. " +
        "Türleri karıştır; 3 öneriden en az biri 'Takipçiler karar verir' olsun (yorumlarda renk oylaması ya da önceki oylamanın sonucu). " +
        "Gerçek anlardan yola çık; sana verilen masaüstü verileri gerçek. Zorlama espri, kalıp şaka, emoji yok. Daha önce önerdiklerini tekrarlama. " +
        "Açıklamalar Türkçe ve doğal: Instagram açıklaması 1-3 cümle ve takipçilere bir soru; TikTok açıklaması tek kısa cümle; YouTube başlığı en çok 60 karakter, sonunda #Shorts; " +
        "YouTube açıklaması 1-2 cümle. Hashtag'ler: 6-10 tane, Türkçe ve İngilizce karışık, # ile başlar, biri #lunapixel.\n\n" +
        "YALNIZCA geçerli JSON döndür, başka hiçbir şey yazma, kod bloğu kullanma. Biçim:\n" +
        "{\"posts\":[{\"day\":\"verilen tarih\",\"type\":\"Masaüstü hayatı | Takipçiler karar verir | Pixel günlüğü\",\"title\":\"kısa başlık\"," +
        "\"idea\":\"neden bu video, tek cümle\",\"music\":\"önerilen müzik havası\",\"scenes\":[{\"title\":\"balonun küçük başlığı, boş olabilir\"," +
        "\"text\":\"balon metni\",\"footer\":\"balonun alt notu, boş olabilir\",\"emote\":\"mutlu\",\"action\":\"\",\"camera\":\"\",\"pose\":\"\",\"wave\":false,\"look\":\"\",\"colors\":{}}]," +
        "\"ig\":\"...\",\"tiktok\":\"...\",\"yt_title\":\"...\",\"yt\":\"...\",\"hashtags\":[\"#...\"]}]}\n" +
        "emote şunlardan biri: mutlu (gülümseme), nese (kahkaha), goz_kirp, sevgi, gurur, utangac, saskin, uzgun, uykulu. " +
        "action sahnenin başındaki beden tepkin: hop (sevinçle zıplama), recoil (irkilip geri sıçrama), shake (titreme, 'yok artık'), nod (onaylama), " +
        "sink (omuzların düşmesi, üzülme), sway (uykulu sallanma), peek (ekranın altından yavaşça çıkma, açılış için iyi) ya da boş. " +
        "camera: close (yakın plan: tam boy pozdan büste kesilir; tepki ve vurgulu anlarda) ya da boş. " +
        "pose: boş (el sallayabildiğin büst), bust (kolların aşağıda büst), stand (tam boy ayakta, görev çubuğunun üstünde), " +
        "sit (görev çubuğunun üstünde yere oturmuş; sakin, içten anlar), walk (soldan yürüyerek ekrana girer, sonra ayakta konuşur; açılış ya da 'geldim' anı). " +
        "Videoyu canlı tut: sahneler arasında poz, tepki ve çekimi değiştir, aynı pozu üst üste kullanma, ilk sahne merak uyandırsın. " +
        "Konuşurken ağzın kendiliğinden oynar, yazı kelime kelime akar. " +
        "wave true ise o sahnede önce el sallarsın (genelde yalnız ilk sahnede). look boşsa bugünkü görünümün kalır. " +
        "colors boş ya da {\"hair\":\"#rrggbb\",\"eyes\":\"#rrggbb\",\"outfit\":\"#rrggbb\",\"ribbon\":\"#rrggbb\"} (hair saç, outfit kıyafet, ribbon kurdele); " +
        "renk oylamasının seçeneklerini ya da sonucunu göstermek için kullan.";

    // Brain (Max aboneliği) ile 3 günlük öneri ister; başarılıysa yeni öneriler (en yenisi başta) döner.
    public static List<Post> Suggest(Config cfg, List<Post> previous, out string error)
    {
        var sb = new StringBuilder();
        sb.AppendLine("Bugün " + DateTime.Now.ToString("d MMMM yyyy dddd, HH:mm", Tr) + ".");
        sb.AppendLine("Önerilerin tarihleri (day alanına aynen yaz): " + string.Join(", ", Enumerable.Range(1, 3).Select(i => DateTime.Today.AddDays(i).ToString("d MMMM dddd", Tr))) + ".");
        // Kayıt tutulmaya başlanmadan önceki günler boş görünür; onları "hiçbir şey olmadı" diye yorumlamasın diye göndermiyoruz.
        var days = Stats.Days(7).SkipWhile(d => d.Done + d.Msgs + d.Breaks + d.Errors == 0).ToList();
        if (days.Count == 0) days = Stats.Days(1);
        sb.AppendLine("Masaüstü verileri (yalnız sayılar; " + days[0].Date.ToString("d MMMM", Tr) + " öncesinin kaydı yok, o günler hakkında bir şey söyleme):");
        foreach (var d in days)
            sb.AppendLine("- " + d.Date.ToString("d MMMM dddd", Tr) + ": " + d.Done + " iş bitti (toplam " + Stats.Dur(d.Minutes) + "), " + d.Msgs + " mesaj, " + d.Breaks + " mola");
        string cur = cfg.Look == "yeni" ? "klasik" : cfg.Look;
        sb.AppendLine("Bugünkü görünümün: " + cur + ". Başka görünümlerin: " + string.Join(", ", Config.Looks().Where(l => l != cur && l != "yeni" && !l.StartsWith("yeni-"))) + ".");
        var col = Config.GroupKeys.Where(k => !string.IsNullOrEmpty(cfg.Colors[k])).Select(k => k + " " + cfg.Colors[k]).ToList();
        sb.AppendLine("Bugünkü renklerin: " + (col.Count == 0 ? "görünümün kendi renkleri" : string.Join(", ", col)) + ".");
        var old = previous.Take(12).Select(p => p.title).Where(t => !string.IsNullOrEmpty(t)).ToList();
        if (old.Count > 0) sb.AppendLine("Daha önce önerdiklerin: " + string.Join(" | ", old) + ".");
        sb.Append("Önümüzdeki 3 gün için önerilerini yaz.");

        string ans = Brain.Studio(cfg, Instructions, sb.ToString(), out error);
        if (ans == null) return null;
        try
        {
            int a = ans.IndexOf('{'), b = ans.LastIndexOf('}');
            var batch = a < 0 || b <= a ? null : new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<PostBatch>(ans.Substring(a, b - a + 1));
            var posts = batch == null || batch.posts == null ? new List<Post>() : batch.posts.Where(p => p != null && p.scenes != null && p.scenes.Count > 0).ToList();
            if (posts.Count == 0) { error = "Öneriler okunamadı, tekrar dene"; Program.LogError(new Exception("Studio: " + ans)); return null; }
            foreach (var p in posts)
            {
                p.created = DateTime.Now.ToString("s");
                p.scenes = p.scenes.Where(s => s != null && !string.IsNullOrEmpty(s.text)).Take(8).ToList();
            }
            return posts;
        }
        catch (Exception ex) { error = "Öneriler okunamadı, tekrar dene"; Program.LogError(new Exception("Studio: " + ans, ex)); return null; }
    }

    public static string Slug(string s)
    {
        var map = new Dictionary<char, char> { { 'ç', 'c' }, { 'ğ', 'g' }, { 'ı', 'i' }, { 'ö', 'o' }, { 'ş', 's' }, { 'ü', 'u' } };
        var sb = new StringBuilder();
        foreach (char ch in (s ?? "").ToLower(Tr))
        {
            char c = map.ContainsKey(ch) ? map[ch] : ch;
            if (c >= 'a' && c <= 'z' || c >= '0' && c <= '9') sb.Append(c);
            else if (sb.Length > 0 && sb[sb.Length - 1] != '-') sb.Append('-');
        }
        string r = sb.ToString().Trim('-');
        return r.Length > 40 ? r.Substring(0, 40).Trim('-') : r == "" ? "video" : r;
    }
}

// Bir öneriyi dikey videoya çevirir. 540×960 tuvalde çizilir, ffmpeg 2 kat büyütür (1080×1920, keskin pikseller).
// Luna'nın pozları (poses.py) bu tuvalde kendi boyunda çizilir. "Çerçeve" (gökyüzü, ay, görev çubuğu, balon ve eski el
// sallayan büst) yarım çözünürlükte (270×480) tasarlanıp Z kat büyütülür: eski kaba pixel görünümü korunur.
// Arka plan gece masaüstü; karakter görev çubuğunun üstünde, balon başının üstünde.
class Reel : IDisposable
{
    public const int W = 540, H = 960, Fps = 30, Z = 2;
    const int CW = W / Z, CH = H / Z, Bar = 24, SpriteW = 192, SpriteH = 256; // çerçeve birimi
    readonly Config cfg;
    readonly List<Scene> scenes;
    readonly List<double> starts = new List<double>();
    public readonly double Duration;
    readonly Dictionary<string, List<Bitmap>> cache = new Dictionary<string, List<Bitmap>>();
    readonly Bitmap background;
    readonly int[,] stars;

    public Reel(Config cfg, Post post)
    {
        this.cfg = cfg;
        scenes = post.scenes ?? new List<Scene>();
        double t = 0;
        foreach (var s in scenes) { starts.Add(t); t += Seconds(s); }
        Duration = Math.Max(t, 1);
        var rnd = new Random(7);
        stars = new int[28, 3];
        for (int i = 0; i < 28; i++) { stars[i, 0] = rnd.Next(6, CW - 6); stars[i, 1] = rnd.Next(6, CH - Bar - SpriteH + 40); stars[i, 2] = rnd.Next(100); }
        background = DrawBackground();
    }

    const double WaveSec = 1.8, WordSec = 0.17, WalkSec = 3.2, StepSec = 0.13;

    // Yazının başladığı an: el sallayan sahnede önce selam, alttan çıkan sahnede önce yerine oturur, sonra konuşma.
    static double TypeStart(Scene s) { return Math.Max(Math.Max(s.wave ? WaveSec : 0.25, s.action == "peek" ? 1.1 : 0), s.pose == "walk" ? WalkSec + 0.2 : 0); }

    static string[] Words(Scene s) { return (s.text ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries); }

    // Süre: yazı kelime kelime akar, sonra en az 2,5 sn (uzun metinde saniyede ~18 harf) ekranda kalır; toplam en az 4,5 sn.
    public static double Seconds(Scene s)
    {
        int n = (s.title ?? "").Length + (s.text ?? "").Length + (s.footer ?? "").Length;
        return Math.Max(4.5, Math.Min(12, TypeStart(s) + Words(s).Length * WordSec + Math.Max(2.5, n / 18.0)));
    }

    public int SceneAt(double t)
    {
        for (int i = starts.Count - 1; i >= 0; i--) if (t >= starts[i]) return i;
        return 0;
    }

    static Color Mix(Color a, Color b, double k)
    {
        return Color.FromArgb((int)(a.R + (b.R - a.R) * k), (int)(a.G + (b.G - a.G) * k), (int)(a.B + (b.B - a.B) * k));
    }

    Bitmap DrawBackground()
    {
        var bmp = new Bitmap(CW, CH, PixelFormat.Format32bppArgb);
        var px = new int[CW * CH];
        Color top = Color.FromArgb(28, 22, 48), mid = Color.FromArgb(70, 44, 92), low = Color.FromArgb(150, 82, 128);
        int sky = CH - Bar;
        // Basamaklı (pixel art) gece gökyüzü; basamak sınırlarında 2×2 düzenli titreşim.
        int[,] bayer = { { 0, 2 }, { 3, 1 } };
        const int steps = 10;
        for (int y = 0; y < sky; y++)
            for (int x = 0; x < CW; x++)
            {
                double k = (double)y / sky * steps + (bayer[y & 1, x & 1] - 1.5) / 4.0 * 0.9;
                int lv = Math.Max(0, Math.Min(steps, (int)Math.Floor(k)));
                double f = (double)lv / steps;
                px[y * CW + x] = (f < 0.55 ? Mix(top, mid, f / 0.55) : Mix(mid, low, (f - 0.55) / 0.45)).ToArgb();
            }
        var data = bmp.LockBits(new Rectangle(0, 0, CW, CH), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
        Marshal.Copy(px, 0, data.Scan0, px.Length);
        bmp.UnlockBits(data);
        using (var g = Graphics.FromImage(bmp))
        {
            // Ay (Luna): sağ üstte, iki krater.
            using (var moon = new SolidBrush(Color.FromArgb(250, 236, 196)))
            using (var crater = new SolidBrush(Color.FromArgb(226, 206, 160)))
            {
                int cx = 222, cy = 44, r = 13;
                for (int y = -r; y <= r; y++)
                {
                    int w = (int)Math.Round(Math.Sqrt(r * r - y * y));
                    g.FillRectangle(moon, cx - w, cy + y, w * 2, 1);
                }
                g.FillRectangle(crater, cx - 6, cy - 4, 4, 3);
                g.FillRectangle(crater, cx + 3, cy + 4, 3, 3);
            }
            // Görev çubuğu: başlat, hesap adı, tepsideki pembe ev simgesi.
            using (var bar = new SolidBrush(Color.FromArgb(24, 20, 34)))
            using (var line = new SolidBrush(Color.FromArgb(70, 58, 96)))
            using (var pink = new SolidBrush(Color.FromArgb(240, 140, 180)))
            using (var dim = new SolidBrush(Color.FromArgb(190, 180, 210)))
            using (var font = new Font("Segoe UI", 9f, FontStyle.Bold, GraphicsUnit.Pixel))
            {
                g.FillRectangle(bar, 0, sky, CW, Bar);
                g.FillRectangle(line, 0, sky, CW, 1);
                for (int i = 0; i < 4; i++) g.FillRectangle(pink, 8 + (i % 2) * 5, sky + 7 + (i / 2) * 5, 4, 4);
                g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit;
                g.DrawString(Studio.Handle, font, dim, 22, sky + 6);
                g.FillRectangle(pink, CW - 15, sky + 10, 5, 3);
                g.FillRectangle(pink, CW - 14, sky + 9, 3, 5);
                g.FillRectangle(line, CW - 22, sky + 7, 1, 10);
            }
        }
        return bmp;
    }

    // "yeni" masaüstü boyundaki yeni çizimdir; videonun ince pikselli pozları (aynı çizim) klasik klasöründe
    string LookOf(Scene s)
    {
        string l = Config.Looks().Contains(s.look ?? "") ? s.look : cfg.Look;
        return l == "yeni" || l.StartsWith("yeni-") ? "klasik" : l; // aksesuarlı yeni görünümlerin video pozu yok
    }

    readonly Dictionary<string, bool> hasPose = new Dictionary<string, bool>();

    // Pozlar (bust: kolları aşağıda büst, stand, sit, walk) poses.py ile üretilir, şimdilik yalnız klasik görünümde var.
    // Görünümde yoksa ya da boşsa el sallayan eski büst ("") kullanılır.
    string PoseOf(Scene s, string want)
    {
        if (string.IsNullOrEmpty(want)) return "";
        string look = LookOf(s), key = look + "|" + want;
        bool ok;
        if (!hasPose.TryGetValue(key, out ok))
        {
            string dir = Sprites.FramesDir(look);
            hasPose[key] = ok = Directory.Exists(dir) && Directory.GetFiles(dir, (want == "walk" ? "walk_" : want + "-idle_") + "*.png").Length > 0;
        }
        return ok ? want : "";
    }

    // withEmote: tam boy pozların ifade kareleri yok (yüz çok küçük), onlarda temel kareler kullanılır.
    List<Bitmap> Frames(Scene s, string prefix, bool withEmote = true)
    {
        string look = LookOf(s);
        string emote = !withEmote ? null : Emotes.Keys.Contains(s.emote ?? "") ? s.emote : "mutlu";
        var colors = new Dictionary<string, string>(cfg.Colors);
        if (s.colors != null)
            foreach (var kv in s.colors)
                if (colors.ContainsKey(kv.Key) && Regex.IsMatch(kv.Value ?? "", "^#[0-9a-fA-F]{6}$")) colors[kv.Key] = kv.Value;
        string key = look + "|" + prefix + "|" + (emote ?? "") + "|" + string.Join(",", Config.GroupKeys.Select(k => colors[k]));
        List<Bitmap> f;
        if (!cache.TryGetValue(key, out f)) cache[key] = f = new Sprites(look, prefix, emote).Render(colors);
        return f;
    }

    public void Draw(Graphics g, double t)
    {
        g.InterpolationMode = InterpolationMode.NearestNeighbor;
        g.PixelOffsetMode = PixelOffsetMode.Half;
        g.SmoothingMode = SmoothingMode.None;
        g.CompositingMode = CompositingMode.SourceCopy;
        g.DrawImage(background, new Rectangle(0, 0, W, H));
        g.CompositingMode = CompositingMode.SourceOver;
        if (scenes.Count == 0) { DrawStars(g, t, Rectangle.Empty); return; }
        int si = SceneAt(t);
        var s = scenes[si];
        double local = t - starts[si], t0 = TypeStart(s);
        var words = Words(s);
        int shown = local < t0 ? 0 : Math.Min(words.Length, (int)((local - t0) / WordSec) + 1);
        bool talking = local >= t0 && shown < words.Length;

        bool close = s.camera == "close";
        // Pozu boş sahne yeni büstle çizilir. Eski el sallayan büst (kaba pikselli, ayrı çizim) yalnız pozlar olmayan
        // görünümlerde kullanılır: yeni çizimle yan yana tutarsız duruyordu.
        string pose = PoseOf(s, string.IsNullOrEmpty(s.pose) ? "bust" : s.pose);
        // Yakın çekim: tam boy pozdan büste kesme. Büyütme yok (2 kat büyütünce pikseller kaba ve gürültülü görünüyordu).
        if (close && pose != "") pose = PoseOf(s, "bust");
        bool walking = pose == "walk" && local < WalkSec;
        if (pose == "walk" && !walking) pose = PoseOf(s, "stand"); // yürüyüp gelir, kameraya dönüp konuşur
        Bitmap frame;
        if (walking)
        {
            var steps = Frames(s, "walk_", false);
            frame = steps[(int)(local / StepSec) % steps.Count];
        }
        else
        {
            bool emo = pose == "" || pose == "bust";
            var wave = s.wave && pose == "" ? Frames(s, "wave_") : null;
            if (wave != null && local < WaveSec) frame = wave[Math.Min(wave.Count - 1, (int)(local / 0.09))];
            else if (talking)
            {
                var talk = Frames(s, pose == "" ? "talk_" : pose + "-talk_", emo);
                frame = talk[(int)((local - t0) / 0.12) % talk.Count];
            }
            else
            {
                var idle = Frames(s, pose == "" ? "idle_" : pose + "-idle_", emo);
                frame = idle[(int)(local / 0.14) % idle.Count];
            }
        }
        int dx, dy;
        Motion(s.action, local, out dx, out dy);
        dx *= Z; dy *= Z;
        int k = pose == "" ? Z : 1; // eski el sallayan büst kaba piksellidir, çerçeve gibi büyütülür
        int fw = frame.Width * k, fh = frame.Height * k, ground = H - Bar * Z;
        int sx = (W - fw) / 2, sy = ground - fh + (pose == "stand" || walking ? 3 * Z : 0); // ayaklar görev çubuğuna basar
        if (walking) sx = (int)(-fw + (sx + fw) * Math.Min(1, local / WalkSec)); // soldan ortaya; adımın inip kalkması karelerde
        int top = sy; // balonun dayandığı baş hizası
        // Balon tam metne göre ölçülür, yazı içine kelime kelime dolar (satır kaymaz).
        bool bubble = local >= t0 - 0.1; // balon yazı başlamadan hemen önce belirir
        var full = new Event { Title = s.title ?? "", Body = s.text ?? "", Footer = s.footer ?? "" };
        var size = Bubble.Layout(full, 220, 6, true);
        int lift = local < t0 + 0.1 ? 4 * Z : 0;
        var brect = new Rectangle((W - size.Width * Z) / 2, Math.Max(4 * Z, top + 10 * Z - size.Height * Z + lift), size.Width * Z, size.Height * Z);
        DrawStars(g, t, bubble ? brect : Rectangle.Empty);
        g.DrawImage(frame, new Rectangle(sx + dx, sy + dy, fw, fh));
        // Aşağı inen (sink, peek) gövde ve ayaklar görev çubuğunun arkasında kalsın.
        g.DrawImage(background, new Rectangle(0, ground, W, Bar * Z), new Rectangle(0, CH - Bar, CW, Bar), GraphicsUnit.Pixel);
        if (!bubble) return;
        var ev = new Event { Title = full.Title, Body = string.Join(" ", words.Take(shown)), Footer = shown >= words.Length ? full.Footer : "" };
        // balon çerçeve biriminde çizilip Z kat büyütülür (kaba pixel yazı, eski boyutunda)
        using (var bb = new Bitmap(size.Width, size.Height, PixelFormat.Format32bppArgb))
        {
            using (var bg = Graphics.FromImage(bb)) Bubble.Draw(bg, new Rectangle(0, 0, size.Width, size.Height), ev, 6, true);
            g.DrawImage(bb, brect);
        }
    }

    // Yıldızlar (çerçeve biriminde, Z kat). Balonun altına denk gelenler çizilmez: yarısı balonun altında kalınca "T" gibi görünüyordu.
    void DrawStars(Graphics g, double t, Rectangle avoid)
    {
        if (!avoid.IsEmpty) avoid.Inflate(8 * Z, 8 * Z); // yıldızın kolları da balona değmesin
        using (var star = new SolidBrush(Color.FromArgb(255, 240, 200)))
        using (var faint = new SolidBrush(Color.FromArgb(150, 140, 190)))
            for (int i = 0; i < stars.GetLength(0); i++)
            {
                int x = stars[i, 0], y = stars[i, 1];
                if (!avoid.IsEmpty && avoid.Contains(x * Z, y * Z)) continue;
                if ((x - 222) * (x - 222) + (y - 44) * (y - 44) <= 17 * 17) continue; // ayın üstüne düşmesin
                if (Math.Sin(t * 1.7 + stars[i, 2]) > 0.55) { g.FillRectangle(star, (x - 1) * Z, y * Z, 3 * Z, Z); g.FillRectangle(star, x * Z, (y - 1) * Z, Z, 3 * Z); }
                else g.FillRectangle(faint, x * Z, y * Z, Z, Z);
            }
    }

    static int Snap(double v) { return (int)Math.Round(v / 4) * 4; } // 4 px: çizimin piksel bloğu, ızgara bozulmasın

    // Sahne başındaki beden tepkisi (ofset, tuval pikseli). Bilinmeyen ya da boş = hareketsiz.
    static void Motion(string action, double t, out int dx, out int dy)
    {
        dx = 0; dy = 0;
        switch (action ?? "")
        {
            case "hop": // sevinçle iki kez zıplar
                if (t < 0.8) dy = -Snap(14 * Math.Abs(Math.Sin(t * Math.PI / 0.4)));
                break;
            case "recoil": // irkilip geri sıçrar, titrer
                if (t < 0.12) dy = -12;
                else if (t < 0.5) { dy = -8; dx = ((int)(t * 30) % 2 == 0) ? 4 : -4; }
                else if (t < 0.65) dy = -4;
                break;
            case "shake": // titreme / "yok artık"
                if (t < 0.7) dx = ((int)(t * 18) % 2 == 0) ? 4 : -4;
                break;
            case "nod": // onaylar gibi iki kez başını eğer
                if (t < 0.9 && (int)(t * 4.5) % 2 == 1) dy = 4;
                break;
            case "sink": // omuzları düşer, yavaşça aşağı iner
                dy = Snap(Math.Min(1, t / 1.2) * 16);
                break;
            case "sway": // uykulu sallanma
                dx = Snap(6 * Math.Sin(t * 2.2));
                break;
            case "peek": // alttan yavaşça çıkar
                dy = Snap(Math.Max(0, 1 - t / 1.0) * 120);
                break;
        }
    }

    public static string Ffmpeg()
    {
        var c = new List<string> { Path.Combine(Config.Dir, "ffmpeg", "ffmpeg.exe") };
        string la = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        c.Add(Path.Combine(la, "Microsoft", "WinGet", "Links", "ffmpeg.exe"));
        try
        {
            string pk = Path.Combine(la, "Microsoft", "WinGet", "Packages");
            if (Directory.Exists(pk))
                foreach (var d in Directory.GetDirectories(pk, "Gyan.FFmpeg*")) c.AddRange(Directory.GetFiles(d, "ffmpeg.exe", SearchOption.AllDirectories));
        }
        catch { }
        foreach (var d in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
            try { if (d.Trim() != "") c.Add(Path.Combine(d.Trim(), "ffmpeg.exe")); } catch { }
        return c.FirstOrDefault(File.Exists);
    }

    // Kareleri ffmpeg'e ham olarak yollar; sessiz ses izi de ekler (düzenleme uygulamaları sesli videoyu daha rahat açıyor). Hata yoksa null.
    public string Export(string path, Action<int> progress)
    {
        string ff = Ffmpeg();
        if (ff == null) return "ffmpeg bulunamadı (kurulum: winget install Gyan.FFmpeg)";
        var psi = new ProcessStartInfo(ff,
            "-y -loglevel error -f rawvideo -pix_fmt bgra -s " + W + "x" + H + " -r " + Fps + " -i - -f lavfi -i anullsrc=r=44100:cl=stereo " +
            "-vf scale=1080:1920:flags=neighbor,format=yuv420p -c:v libx264 -preset medium -crf 18 -tune animation -c:a aac -b:a 128k -shortest -movflags +faststart \"" + path + "\"")
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardError = true, StandardErrorEncoding = Encoding.UTF8,
        };
        try
        {
            using (var p = Process.Start(psi))
            {
                var err = p.StandardError.ReadToEndAsync();
                var input = p.StandardInput.BaseStream;
                int total = (int)Math.Ceiling(Duration * Fps);
                var buf = new byte[W * H * 4];
                try
                {
                    using (var bmp = new Bitmap(W, H, PixelFormat.Format32bppArgb))
                    using (var g = Graphics.FromImage(bmp))
                        for (int i = 0; i < total; i++)
                        {
                            Draw(g, i / (double)Fps);
                            var data = bmp.LockBits(new Rectangle(0, 0, W, H), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
                            Marshal.Copy(data.Scan0, buf, 0, buf.Length);
                            bmp.UnlockBits(data);
                            input.Write(buf, 0, buf.Length);
                            if (progress != null && i % 15 == 0) progress(i * 100 / total);
                        }
                    input.Close();
                }
                catch (IOException) { } // ffmpeg erken kapandıysa sebebi aşağıda stderr'de
                if (!p.WaitForExit(180000)) { try { p.Kill(); } catch { } return "ffmpeg çok uzun sürdü"; }
                if (p.ExitCode != 0 || !File.Exists(path))
                {
                    Program.LogError(new Exception("ffmpeg: " + err.Result));
                    return "ffmpeg hatası: " + err.Result.Split('\n').FirstOrDefault(l => l.Trim() != "");
                }
                if (progress != null) progress(100);
                return null;
            }
        }
        catch (Exception ex) { Program.LogError(ex); return "Video yapılamadı: " + ex.Message; }
    }

    public void Dispose()
    {
        foreach (var l in cache.Values) foreach (var b in l) b.Dispose();
        cache.Clear();
        background.Dispose();
    }
}

// Uygulamadaki Stüdyo sayfası: öneriler listesi, ayrıntılar, kopyalama düğmeleri, canlı önizleme ve video üretimi.
class StudioForm : Form
{
    static readonly Color Bg = Color.FromArgb(32, 30, 40), Box = Color.FromArgb(44, 42, 56), Dim = Color.FromArgb(170, 165, 185), Pink = Color.FromArgb(240, 140, 180);
    readonly Config cfg;
    List<Post> posts;
    readonly ListBox list = new ListBox();
    readonly TextBox detail = new TextBox();
    readonly PictureBox preview = new PictureBox();
    readonly Label status = new Label(), progress = new Label();
    readonly Button gen, make, openVideo;
    readonly List<Button> copyButtons = new List<Button>();
    readonly System.Windows.Forms.Timer play = new System.Windows.Forms.Timer { Interval = 66 };
    readonly Stopwatch clock = new Stopwatch();
    readonly Bitmap canvas = new Bitmap(Reel.W, Reel.H, PixelFormat.Format32bppArgb);
    Reel reel;
    bool busy;

    public static StudioForm Embedded(Config cfg) { return new StudioForm(cfg); }

    StudioForm(Config cfg)
    {
        this.cfg = cfg;
        Font = new Font("Segoe UI", 10f);
        BackColor = Bg;
        ForeColor = Color.FromArgb(235, 232, 240);
        ClientSize = new Size(800, 660);

        Controls.Add(new Label { Text = "Stüdyo", Left = 20, Top = 14, AutoSize = true, Font = new Font("Segoe UI", 18f, FontStyle.Bold) });
        Controls.Add(new Label { Text = "Luna · " + Studio.Handle + " · Reels, TikTok, Shorts", Left = 22, Top = 54, AutoSize = true, ForeColor = Dim });
        gen = Btn("Yeni öneriler iste", 330, 18, 170, 34);
        gen.ForeColor = Pink;
        gen.Click += (s, e) => Generate();
        status.SetBounds(20, 78, 490, 22);
        status.ForeColor = Dim;
        Controls.Add(status);

        list.SetBounds(20, 104, 200, 270);
        list.BackColor = Box; list.ForeColor = ForeColor; list.BorderStyle = BorderStyle.None;
        list.DrawMode = DrawMode.OwnerDrawFixed; list.ItemHeight = 48;
        list.DrawItem += DrawItem;
        list.SelectedIndexChanged += (s, e) => ShowPost();
        Controls.Add(list);

        Controls.Add(new Label { Text = "Kopyala", Left = 20, Top = 384, AutoSize = true, ForeColor = Pink, Font = new Font("Segoe UI", 10f, FontStyle.Bold) });
        string[] copyLabels = { "Instagram açıklaması", "TikTok açıklaması", "YouTube başlığı", "YouTube açıklaması", "Hashtag'ler" };
        for (int i = 0; i < copyLabels.Length; i++)
        {
            int which = i;
            var b = Btn(copyLabels[i], 20, 412 + i * 38, 200, 32);
            b.TextAlign = ContentAlignment.MiddleLeft;
            b.Click += (s, e) => Copy(which, copyLabels[which]);
            copyButtons.Add(b);
        }

        detail.SetBounds(230, 104, 280, 524);
        detail.Multiline = true; detail.ReadOnly = true; detail.ScrollBars = ScrollBars.Vertical; detail.WordWrap = true;
        detail.BackColor = Box; detail.ForeColor = ForeColor; detail.BorderStyle = BorderStyle.None;
        Controls.Add(detail);

        preview.SetBounds(522, 18, Reel.W / 2, Reel.H / 2);
        preview.Paint += (s, e) =>
        {
            e.Graphics.InterpolationMode = InterpolationMode.HighQualityBilinear;
            e.Graphics.PixelOffsetMode = PixelOffsetMode.Half;
            e.Graphics.DrawImage(canvas, new Rectangle(0, 0, Reel.W / 2, Reel.H / 2));
        };
        Controls.Add(preview);
        make = Btn("Videoyu üret (1080×1920 MP4)", 522, 508, Reel.W / 2, 34);
        make.ForeColor = Pink;
        make.Click += (s, e) => MakeVideo();
        progress.SetBounds(522, 546, Reel.W / 2, 40);
        progress.ForeColor = Dim;
        Controls.Add(progress);
        openVideo = Btn("Videoyu aç", 522, 592, 132, 32);
        openVideo.Click += (s, e) => { var p = Selected(); if (p != null && File.Exists(p.video ?? "")) try { Process.Start(p.video); } catch { } };
        var openDir = Btn("Klasörü aç", 660, 592, 132, 32);
        openDir.Click += (s, e) =>
        {
            var p = Selected();
            try { Process.Start("explorer.exe", p != null && File.Exists(p.video ?? "") ? "/select,\"" + p.video + "\"" : "\"" + Studio.VideoDir + "\""); } catch { }
        };

        play.Tick += (s, e) => { if (Visible && reel != null) RenderPreview(); };
        play.Start();
        posts = Studio.Load();
        Fill(0);
        if (posts.Count == 0) status.Text = "Henüz öneri yok. \"Yeni öneriler iste\"ye bas, Luna 3 günlük plan yazsın.";
    }

    Button Btn(string text, int x, int y, int w, int h)
    {
        var b = new Button { Text = text, Left = x, Top = y, Width = w, Height = h, FlatStyle = FlatStyle.Flat, Cursor = Cursors.Hand };
        b.FlatAppearance.BorderColor = Color.FromArgb(80, 72, 100);
        Controls.Add(b);
        return b;
    }

    Post Selected() { return list.SelectedIndex >= 0 && list.SelectedIndex < posts.Count ? posts[list.SelectedIndex] : null; }

    void Fill(int select)
    {
        list.Items.Clear();
        foreach (var p in posts) list.Items.Add(p.title ?? "");
        if (posts.Count > 0) list.SelectedIndex = Math.Min(select, posts.Count - 1);
        else ShowPost();
    }

    void DrawItem(object sender, DrawItemEventArgs e)
    {
        if (e.Index < 0 || e.Index >= posts.Count) return;
        var p = posts[e.Index];
        bool sel = (e.State & DrawItemState.Selected) != 0;
        using (var bg = new SolidBrush(sel ? Color.FromArgb(56, 44, 70) : Box)) e.Graphics.FillRectangle(bg, e.Bounds);
        using (var small = new Font("Segoe UI", 8.5f))
        using (var bold = new Font("Segoe UI", 9.5f, FontStyle.Bold))
        {
            TextRenderer.DrawText(e.Graphics, (p.day ?? "") + (string.IsNullOrEmpty(p.video) ? "" : "  · video hazır"), small, new Rectangle(e.Bounds.X + 8, e.Bounds.Y + 5, e.Bounds.Width - 12, 18), Pink, TextFormatFlags.EndEllipsis);
            TextRenderer.DrawText(e.Graphics, p.title ?? "", bold, new Rectangle(e.Bounds.X + 8, e.Bounds.Y + 23, e.Bounds.Width - 12, 20), Color.White, TextFormatFlags.EndEllipsis);
        }
    }

    void ShowPost()
    {
        var p = Selected();
        if (reel != null) { reel.Dispose(); reel = null; }
        foreach (var b in copyButtons) b.Enabled = p != null;
        make.Enabled = p != null && !busy;
        openVideo.Enabled = p != null && File.Exists(p.video ?? "");
        progress.Text = p != null && File.Exists(p.video ?? "") ? "Hazır: " + Path.GetFileName(p.video) : "";
        if (p == null) { detail.Text = ""; using (var g = Graphics.FromImage(canvas)) g.Clear(Box); preview.Invalidate(); return; }
        var sb = new StringBuilder();
        string nl = Environment.NewLine;
        sb.Append(p.day + " · " + p.type + nl + p.title + nl + nl);
        if (!string.IsNullOrEmpty(p.idea)) sb.Append(p.idea + nl + nl);
        double total = 0;
        for (int i = 0; i < p.scenes.Count; i++)
        {
            var s = p.scenes[i];
            double sec = Reel.Seconds(s);
            total += sec;
            sb.Append("Sahne " + (i + 1) + " (" + sec.ToString("0.#") + " sn, " + (s.emote ?? "mutlu") + (s.wave ? ", el sallar" : "") +
                (string.IsNullOrEmpty(s.action) ? "" : ", " + s.action) + (s.camera == "close" ? ", yakın" : "") +
                (string.IsNullOrEmpty(s.pose) ? "" : ", " + s.pose) + ")" + nl);
            if (!string.IsNullOrEmpty(s.title)) sb.Append("[" + s.title + "] ");
            sb.Append(s.text + nl);
            if (!string.IsNullOrEmpty(s.footer)) sb.Append("(" + s.footer + ")" + nl);
            sb.Append(nl);
        }
        sb.Append("Toplam ~" + Math.Round(total) + " sn" + (string.IsNullOrEmpty(p.music) ? "" : " · Müzik: " + p.music) + nl + nl);
        sb.Append("Instagram:" + nl + p.ig + nl + nl + "TikTok:" + nl + p.tiktok + nl + nl + "YouTube: " + p.yt_title + nl + p.yt + nl + nl + p.Tags());
        detail.Text = sb.ToString();
        try { reel = new Reel(cfg, p); clock.Restart(); RenderPreview(); }
        catch (Exception ex) { Program.LogError(ex); }
    }

    void RenderPreview()
    {
        double t = clock.Elapsed.TotalSeconds % reel.Duration;
        using (var g = Graphics.FromImage(canvas)) reel.Draw(g, t);
        preview.Invalidate();
    }

    void Copy(int which, string label)
    {
        var p = Selected();
        if (p == null) return;
        string tags = p.Tags(), nl = Environment.NewLine;
        string text = which == 0 ? p.ig + nl + nl + tags : which == 1 ? p.tiktok + " " + tags : which == 2 ? p.yt_title : which == 3 ? p.yt + nl + nl + tags : tags;
        try { Clipboard.SetText((text ?? "").Trim()); status.Text = "Kopyalandı: " + label; }
        catch { status.Text = "Panoya kopyalanamadı, tekrar dene"; }
    }

    void SetBusy(bool on)
    {
        busy = on;
        gen.Enabled = !on;
        make.Enabled = !on && Selected() != null;
    }

    void Generate()
    {
        if (busy) return;
        if (!Brain.Available(cfg)) { status.Text = "Öneri için Claude Code gerekiyor (Ayarlar → yapay zekâ)."; return; }
        SetBusy(true);
        status.Text = "Luna düşünüyor… (1-3 dakika sürebilir)";
        var previous = posts.ToList();
        Task.Run(() => { string err; var r = Studio.Suggest(cfg, previous, out err); return Tuple.Create(r, err); })
            .ContinueWith(t => BeginInvoke((Action)(() =>
            {
                SetBusy(false);
                if (t.Result.Item1 == null) { status.Text = "Olmadı: " + (t.Result.Item2 ?? "cevap gelmedi"); return; }
                posts.InsertRange(0, t.Result.Item1);
                Studio.Save(posts);
                Fill(0);
                status.Text = t.Result.Item1.Count + " yeni öneri hazır. Birini seç, sağda önizlemesi oynuyor.";
            })));
    }

    void MakeVideo()
    {
        var p = Selected();
        if (p == null || busy) return;
        SetBusy(true);
        progress.Text = "Video hazırlanıyor… %0";
        string path = Path.Combine(Studio.VideoDir, DateTime.Now.ToString("yyyy-MM-dd_HHmm") + "_" + Studio.Slug(p.title) + ".mp4");
        Task.Run(() =>
        {
            using (var r = new Reel(cfg, p))
                return r.Export(path, pct => BeginInvoke((Action)(() => progress.Text = "Video hazırlanıyor… %" + pct)));
        }).ContinueWith(t => BeginInvoke((Action)(() =>
        {
            SetBusy(false);
            if (t.Result != null) { progress.Text = t.Result; return; }
            p.video = path;
            Studio.Save(posts);
            list.Invalidate();
            openVideo.Enabled = true;
            progress.Text = "Hazır: " + Path.GetFileName(path);
        })));
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) { play.Dispose(); if (reel != null) reel.Dispose(); canvas.Dispose(); }
        base.Dispose(disposing);
    }
}
