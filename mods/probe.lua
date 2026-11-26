-- local debug probe (not part of upstream)
return {
  name = "probe",
  description = "Return settings and timing internals for debugging",
  schema = {},
  execute = function(_, send_response)
    local keys = {}
    if G and G.SETTINGS then
      for k, v in pairs(G.SETTINGS) do
        if type(v) ~= "table" then keys[k] = tostring(v) end
      end
    end
    send_response({
      gamespeed = G and G.SETTINGS and tostring(G.SETTINGS.GAMESPEED) or "NO_SETTINGS",
      speedfactor = G and tostring(G.SPEEDFACTOR) or "nil",
      fps_cap = G and tostring(G.FPS_CAP) or "nil",
      animation_fps = G and tostring(G.ANIMATION_FPS) or "nil",
      paused = G and G.SETTINGS and tostring(G.SETTINGS.paused) or "nil",
      state = G and tostring(G.STATE) or "nil",
      settings_keys = keys,
      env = {
        BALATROBOT_FAST = os.getenv("BALATROBOT_FAST") or "",
        BALATROBOT_GAMESPEED = os.getenv("BALATROBOT_GAMESPEED") or "",
      },
    })
  end,
}
