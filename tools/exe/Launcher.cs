// Angry Birds Space Archipelago.exe: opens the game-styled launcher straight away (no Archipelago Launcher
// window). The launcher itself is the "Angry Birds Space Launcher" component of the apworld, so this exe only
// finds Archipelago, starts that component and shows a small splash while Archipelago loads.
// Built by tools/build.py with the C# compiler that ships with Windows (.NET Framework 4).
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using Microsoft.Win32;

static class Program
{
    const string Title = "Angry Birds Space Archipelago";  // window title of the launcher

    static string FindArchipelago()
    {
        // 1) the archipelago:// handler the Archipelago installer registers
        foreach (RegistryKey root in new[] { Registry.CurrentUser, Registry.LocalMachine })
        {
            using (RegistryKey k = root.OpenSubKey(@"Software\Classes\archipelago\shell\open\command"))
            {
                string cmd = k == null ? null : k.GetValue("") as string;
                if (string.IsNullOrEmpty(cmd)) continue;
                cmd = cmd.Trim();
                string exe = cmd.StartsWith("\"") ? cmd.Substring(1, cmd.IndexOf('"', 1) - 1) : cmd.Split(' ')[0];
                string launcher = Path.Combine(Path.GetDirectoryName(exe), "ArchipelagoLauncher.exe");
                if (File.Exists(launcher)) return launcher;
            }
        }
        // 2) the default install folder
        string def = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                                  "Archipelago", "ArchipelagoLauncher.exe");
        return File.Exists(def) ? def : null;
    }

    static bool LauncherWindowOpen()
    {
        foreach (Process p in Process.GetProcessesByName("ArchipelagoLauncher"))
        {
            try { if (p.MainWindowTitle == Title) return true; } catch { }
        }
        return false;
    }

    [STAThread]
    static void Main()
    {
        Application.EnableVisualStyles();
        if (LauncherWindowOpen()) return;  // already open
        string launcher = FindArchipelago();
        if (launcher == null)
        {
            MessageBox.Show("Archipelago is not installed.\n\nInstall it from https://archipelago.gg, put " +
                            "angrybirdsspace.apworld in its custom_worlds folder and try again.", Title,
                            MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        Process.Start(new ProcessStartInfo(launcher, "\"Angry Birds Space Launcher\"")
        {
            WorkingDirectory = Path.GetDirectoryName(launcher),
            UseShellExecute = false,
        });

        // splash until the launcher window shows up (Archipelago takes a few seconds to load its worlds)
        Form splash = new Form
        {
            FormBorderStyle = FormBorderStyle.None, StartPosition = FormStartPosition.CenterScreen,
            Size = new Size(420, 130), BackColor = Color.FromArgb(28, 51, 84), ShowInTaskbar = true, Text = Title,
            TopMost = true,
        };
        Icon icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        splash.Icon = icon;
        splash.Controls.Add(new PictureBox { Image = new Icon(icon, 64, 64).ToBitmap(), SizeMode = PictureBoxSizeMode.CenterImage,
                                             Location = new Point(18, 33), Size = new Size(64, 64) });
        splash.Controls.Add(new Label { Text = "Angry Birds Space Archipelago", ForeColor = Color.FromArgb(190, 240, 60),
                                        Font = new Font("Segoe UI", 15, FontStyle.Bold), AutoSize = true, Location = new Point(96, 36) });
        splash.Controls.Add(new Label { Text = "Starting...", ForeColor = Color.White, Font = new Font("Segoe UI", 10),
                                        AutoSize = true, Location = new Point(99, 72) });
        DateTime started = DateTime.Now;
        Timer t = new Timer { Interval = 400 };
        t.Tick += (s, e) => { if (LauncherWindowOpen() || (DateTime.Now - started).TotalSeconds > 60) splash.Close(); };
        t.Start();
        Application.Run(splash);
    }
}
