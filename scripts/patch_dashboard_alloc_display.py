with open('frontend/src/pages/Dashboard.jsx', 'r', encoding='utf-8') as f:
    c = f.read()

target = """                                      {/* Citizen-Facing Resource Summary: Plain text, maximum eight resources */}
                                      {(() => {
                                        const confirmed = (entry.missionUpdate.confirmed_resources || [])
                                          .filter(r => Number(r.quantity) > 0);
                                        const totalCount = confirmed.length;
                                        
                                        // Deterministic stable ordering: sort by allocated quantity descending, then alphabetical by name
                                        const displayed = [...confirmed]
                                          .sort((a, b) => (Number(b.quantity) - Number(a.quantity)) || a.resource_name.localeCompare(b.resource_name))
                                          .slice(0, 8);

                                        return (
                                          <div className="flex flex-col gap-1.5 text-xs text-slate-700 pt-1">
                                            <span className="font-bold text-slate-800">Resources allocated</span>
                                            {totalCount === 0 ? (
                                              <p className="text-slate-500 italic pl-1">No resources allocated yet</p>
                                            ) : ("""

replacement = """                                      {/* Citizen-Facing Resource Summary: Plain text, maximum eight resources */}
                                      {(() => {
                                        const confirmed = (entry.missionUpdate.confirmed_resources || [])
                                          .filter(r => Number(r.quantity) > 0);
                                        const totalCount = confirmed.length;
                                        const allocStatus = entry.missionUpdate.allocation_status;
                                        const isPending = entry.status === 'ORCHESTRATING' || allocStatus === 'PENDING';
                                        const isFailed = allocStatus === 'FAILED';
                                        const isNoStock = allocStatus === 'NO_STOCK_AVAILABLE' || allocStatus === 'STOCK_EXHAUSTED';
                                        const isPartiallyFulfilled = entry.missionUpdate.fulfilment_status === 'PARTIALLY_FULFILLED' || allocStatus === 'PARTIALLY_FULFILLED';
                                        
                                        // Deterministic stable ordering: sort by allocated quantity descending, then alphabetical by name
                                        const displayed = [...confirmed]
                                          .sort((a, b) => (Number(b.quantity) - Number(a.quantity)) || a.resource_name.localeCompare(b.resource_name))
                                          .slice(0, 8);

                                        return (
                                          <div className="flex flex-col gap-1.5 text-xs text-slate-700 pt-1">
                                            <div className="flex items-center justify-between">
                                              <span className="font-bold text-slate-800">Resources allocated</span>
                                              {isPartiallyFulfilled && totalCount > 0 && (
                                                <span className="text-[10px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                                                  Partially Fulfilled
                                                </span>
                                              )}
                                              {allocStatus === 'FULLY_FULFILLED' && totalCount > 0 && (
                                                <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                                                  Fully Allocated
                                                </span>
                                              )}
                                            </div>
                                            {isPending && totalCount === 0 ? (
                                              <p className="text-slate-500 italic pl-1 flex items-center gap-1.5">
                                                <span className="inline-block w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
                                                <span>Allocation in progress...</span>
                                              </p>
                                            ) : isFailed && totalCount === 0 ? (
                                              <p className="text-rose-600 italic pl-1">
                                                Resource allocation unavailable (allocation failed)
                                              </p>
                                            ) : isNoStock && totalCount === 0 ? (
                                              <p className="text-amber-700 italic pl-1">
                                                No inventory in stock for required supplies (shortage reported)
                                              </p>
                                            ) : totalCount === 0 ? (
                                              <p className="text-slate-500 italic pl-1">No resources allocated yet</p>
                                            ) : ("""

assert target in c, "target not found in Dashboard.jsx"
c = c.replace(target, replacement, 1)

with open('frontend/src/pages/Dashboard.jsx', 'w', encoding='utf-8') as f:
    f.write(c)

print('Successfully patched Dashboard.jsx')
