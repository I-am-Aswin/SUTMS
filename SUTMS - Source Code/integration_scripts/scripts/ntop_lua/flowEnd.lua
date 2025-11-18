local file = "/var/lib/ntopng/protocols.txt"
local flow = interface.getFlowInfo()

if flow ~= nil then
  local proto = flow["proto.l7_name"] or "unknown"
  if proto ~= "unknown" then
    ntop.logInfo("Detected protocol: " .. proto)
    local f = io.open(file, "a")
    if f then
      f:write(proto .. "\n")
      f:close()
    else
      ntop.logError("Cannot open file for writing: " .. file)
    end
  end
end
