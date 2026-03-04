import { useState, useMemo } from "react";
import { DocumentItem } from "../../types";

type PropType = {
    documents: DocumentItem[];
};

export default function TaxHelpCard({ documents }: PropType) {
    const [activeSegment, setActiveSegment] = useState<"overview" | "details">("overview");

    // Filter for docs that actually have parsed tax data
    const taxDocs = useMemo(() => {
        return documents.filter(doc => doc.tax_data_json && doc.tax_data_json !== "{}" && doc.tax_data_json !== "null");
    }, [documents]);

    const taxTotals = useMemo(() => {
        return taxDocs.reduce((acc, doc) => {
            try {
                const data = JSON.parse(doc.tax_data_json || "{}");
                acc.maintenance += (data.maintenanceCosts || 0);
                acc.admin += (data.adminFees || 0);
                acc.insurance += (data.insurance || 0);
                acc.service35a += (data.serviceCharges35a || 0);
                acc.handyman35a += (data.handyman35a || 0);
                acc.other += (data.otherDeductible || 0);
            } catch (e) {
                // ignore parsing errors
            }
            return acc;
        }, { maintenance: 0, admin: 0, insurance: 0, service35a: 0, handyman35a: 0, other: 0 });
    }, [taxDocs]);

    const totalDeductible = taxTotals.service35a + taxTotals.handyman35a + taxTotals.other;

    const exportTaxDataToCSV = () => {
        if (taxDocs.length === 0) {
            alert("Keine Steuerdaten zum Exportieren gefunden.");
            return;
        }

        const headers = [
            "Dokument",
            "Datum",
            "Instandhaltung (€)",
            "Verwaltergebühr (€)",
            "Versicherung (€)",
            "Haushaltsnahe Dienstleistungen (§35a) (€)",
            "Handwerkerleistungen (§35a) (€)",
            "Sonstige absetzbare Kosten (€)"
        ];

        const rows = taxDocs.map(doc => {
            let data: any = {};
            try { data = JSON.parse(doc.tax_data_json || "{}"); } catch (e) { }
            return [
                doc.filename,
                doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : "",
                (data.maintenanceCosts || 0).toFixed(2),
                (data.adminFees || 0).toFixed(2),
                (data.insurance || 0).toFixed(2),
                (data.serviceCharges35a || 0).toFixed(2),
                (data.handyman35a || 0).toFixed(2),
                (data.otherDeductible || 0).toFixed(2)
            ];
        });

        const csvContent = [
            headers.join(";"),
            ...rows.map(row => row.join(";"))
        ].join("\n");

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `ndiah_Steuerdaten_${new Date().getFullYear()}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div className="bg-white border rounded-lg shadow-sm w-full md:w-96 flex flex-col flex-shrink-0 animate-in fade-in slide-in-from-bottom-2">
            <div className="p-4 border-b flex items-center justify-between">
                <h2 className="font-semibold text-gray-800">Steuerhilfe (§35a EStG)</h2>
                <span className="text-xs bg-brand-100 text-brand-800 px-2 py-0.5 rounded-full font-medium">BETA</span>
            </div>

            <div className="flex border-b text-sm">
                <button
                    onClick={() => setActiveSegment("overview")}
                    className={`flex-1 py-2 text-center font-medium ${activeSegment === "overview" ? "text-brand-600 border-b-2 border-brand-600" : "text-gray-500 hover:text-gray-700"
                        }`}
                >
                    Übersicht
                </button>
                <button
                    onClick={() => setActiveSegment("details")}
                    className={`flex-1 py-2 text-center font-medium ${activeSegment === "details" ? "text-brand-600 border-b-2 border-brand-600" : "text-gray-500 hover:text-gray-700"
                        }`}
                >
                    Details
                </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto">
                {taxDocs.length === 0 ? (
                    <div className="text-center py-8 text-sm text-gray-500">
                        <p>Keine steuerlich relevanten Daten in den Dokumenten gefunden.</p>
                        <p className="mt-2 text-xs">Laden Sie Ihre Jahresabrechnung hoch, um hier §35a-Bescheinigungen zu sehen.</p>
                    </div>
                ) : (
                    <>
                        {activeSegment === "overview" && (
                            <div className="space-y-6">
                                <div className="bg-gray-50 p-4 rounded-lg flex flex-col items-center justify-center">
                                    <span className="text-sm text-gray-500 font-medium mb-1">Potenziell absetzbar (Summe)</span>
                                    <span className="text-3xl font-bold text-gray-900">{totalDeductible.toFixed(2)} €</span>
                                </div>

                                <div className="space-y-3">
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-gray-600">Haushaltsnahe DL (§35a)</span>
                                        <span className="font-medium">{taxTotals.service35a.toFixed(2)} €</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-gray-600">Handwerkerkosten (§35a)</span>
                                        <span className="font-medium">{taxTotals.handyman35a.toFixed(2)} €</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-gray-600">Sonstiges absetzbar</span>
                                        <span className="font-medium">{taxTotals.other.toFixed(2)} €</span>
                                    </div>
                                </div>

                                <button
                                    onClick={exportTaxDataToCSV}
                                    className="w-full mt-4 bg-brand-600 hover:bg-brand-700 text-white py-2 rounded-md font-medium transition-colors"
                                >
                                    Daten als CSV exportieren
                                </button>
                            </div>
                        )}

                        {activeSegment === "details" && (
                            <div className="space-y-4">
                                {taxDocs.map(doc => {
                                    let data: any = {};
                                    try { data = JSON.parse(doc.tax_data_json || "{}"); } catch (e) { }

                                    return (
                                        <div key={doc.document_id} className="border rounded-md p-3 text-sm">
                                            <p className="font-medium text-gray-900 truncate mb-2" title={doc.filename}>{doc.filename}</p>
                                            <div className="space-y-1 text-xs text-gray-600">
                                                {data.serviceCharges35a > 0 && <div className="flex justify-between"><span>Haushaltsnahe DL:</span> <span>{data.serviceCharges35a.toFixed(2)} €</span></div>}
                                                {data.handyman35a > 0 && <div className="flex justify-between"><span>Handwerker:</span> <span>{data.handyman35a.toFixed(2)} €</span></div>}
                                                {data.maintenanceCosts > 0 && <div className="flex justify-between"><span>Instandhaltung:</span> <span>{data.maintenanceCosts.toFixed(2)} €</span></div>}
                                                {data.adminFees > 0 && <div className="flex justify-between"><span>Verwaltergebühr:</span> <span>{data.adminFees.toFixed(2)} €</span></div>}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
