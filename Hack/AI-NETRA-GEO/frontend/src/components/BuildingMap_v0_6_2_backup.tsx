"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";

import type {
  Feature,
  FeatureCollection,
  Geometry,
  Point,
} from "geojson";

// ============================================================
// 1. CONFIGURATION
// ============================================================

const BUILDING_API = "http://127.0.0.1:8000";

const WATERLOGGING_API = "http://127.0.0.1:8001";

const HISTORICAL_FLOOD_GEOJSON_URL = "/geojson/historical_flood_2020.geojson";

const DEFAULT_CENTER: [number, number] = [
  17.371,
  78.512,
];

// ============================================================
// 2. TYPES
// ============================================================

type HeightQualityFlag =
  | "unverified_estimate"
  | "review_low_estimate"
  | "unavailable";

type SourceInvestigation = {
  source: string;
  status: string;
  access_method?: string;
  attributes_found?: Record<string, unknown>;
  attributes_missing?: string[];
  source_timestamp?: string | null;
  dataset_year?: number;
  verification?: string;
};

type SourceInvestigationReport = {
  sources_checked: number;
  sources_pending: number;
  investigations: SourceInvestigation[];
};

type NearbyCandidate = {
  building_id: string;
  distance_m: number;

  building_type?: string | null;

  estimated_height_m?: number | null;
  height_quality_flag?: HeightQualityFlag;

  footprint_area_m2?: number | null;
  area_verification?: string | null;

  distance_to_musi_water_m?: number | null;
  river_proximity_band?: string | null;

  nearest_waterlogging_location?: string | null;
  distance_to_waterlogging_point_m?: number | null;
  waterlogging_proximity_band?: string | null;

  // Historical mapped flood-area intersection (not confirmed flooding)
  historical_polygon_overlap_pct?: number | null;
  historical_polygon_overlap_category?: string | null;
  historical_polygon_has_overlap?: boolean | null;
  historical_polygon_evidence_status?: string | null;
  building_flooding_confirmed?: boolean;

  geometry?: Geometry;
};

type RiverDistanceEvidence = {
  value: number | null;
  source?: string | null;
  verification_status?: string;
  calculation_method?: string | null;
  river_geometry_type?: string | null;
  river_geometry_ids?: string | null;
};

type WaterloggingDistanceEvidence = {
  value: number | null;
  unit?: string;
  source?: string | null;
  measurement_type?: string;
  geometry_type?: string;
  nearest_location?: string | null;
  nearest_location_id?: string | number | null;
  verification_status?: string;
  calculation_method?: string | null;
  observation_date?: string | null;
  water_depth_m?: number | null;
  confidence?: number | null;
  historical_flood_confirmed?: boolean;
  building_flooding_confirmed?: boolean;
  flood_risk_assigned?: boolean;
};

type HistoricalFloodAreaEvidence = {
  value?: number | null;
  unit?: string | null;
  source?: string | null;
  source_file?: string | null;
  source_geometry_file?: string | null;
  historical_period?: string | null;
  measurement_type?: string | null;
  verification_status?: string | null;
  building_area_in_pilot_m2?: number | null;
  overlap_area_m2?: number | null;
  overlap_category?: string | null;
  building_flooding_confirmed?: boolean;
  historical_flood_confirmed?: boolean;
  flood_risk_assigned?: boolean;
  note?: string | null;
};

type BuildingResult = {
  match_type: "exact" | "none" | "error";

  building_id?: string;

  latitude?: number;
  longitude?: number;

  message?: string;

  // Building identification
  building_type?: string | null;
  building_levels?: string | null;
  height?: string | null;
  construction_date?: string | null;

  source?: string;
  source_timestamp?: string | null;

  // Google height intelligence
  estimated_height_m?: number | null;
  height_estimate_source?: string | null;
  height_estimate_year?: number | null;
  height_verification?: string | null;
  height_sampling_method?: string | null;
  height_quality_flag?: HeightQualityFlag;

  // Building footprint
  footprint_area_m2?: number | null;
  area_source?: string | null;
  area_method?: string | null;
  area_verification?: string | null;

  // Musi River proximity
  distance_to_musi_water_m?: number | null;
  river_proximity_band?: string | null;
  intersects_mapped_water?: boolean | null;
  river_source?: string | null;
  river_distance_method?: string | null;
  river_verification?: string | null;

  // Government waterlogging proximity
  nearest_waterlogging_location?: string | null;
  nearest_waterlogging_id?: string | number | null;
  distance_to_waterlogging_point_m?: number | null;
  waterlogging_proximity_band?: string | null;
  waterlogging_source?: string | null;
  waterlogging_distance_method?: string | null;
  waterlogging_verification?: string | null;

  // Historical mapped flood-area intersection
  historical_polygon_overlap_pct?: number | null;
  historical_polygon_overlap_m2?: number | null;
  historical_polygon_overlap_category?: string | null;
  historical_polygon_has_overlap?: boolean | null;
  historical_polygon_source?: string | null;
  historical_polygon_evidence_status?: string | null;

  historical_flood_confirmed?: boolean;
  building_flooding_confirmed?: boolean;
  flood_risk_assigned?: boolean;

  // Evidence
  attribute_evidence?: {
    estimated_height?: {
      confidence?: number | null;
    };

    river_distance?: RiverDistanceEvidence;

    waterlogging_distance?: WaterloggingDistanceEvidence;
    historical_flood_area_overlap?: HistoricalFloodAreaEvidence;
  };

  geometry?: Geometry;

  source_investigation?: SourceInvestigationReport;

  nearby_candidates?: NearbyCandidate[];

  search_radius_m?: number;
};

type WaterloggingProperties = {
  waterlogging_id?: number | null;
  name?: string | null;
  classification?: string;
  source?: string;
  source_layer?: string;
  original_folder?: string | null;
  observation_date?: string | null;
  water_depth_m?: number | null;
  duration_hours?: number | null;
  verification_status?: string;
  building_flooding_confirmed?: boolean;
};

type WaterloggingFeature = Feature<
  Point,
  WaterloggingProperties
>;

type WaterloggingCollection = FeatureCollection<
  Point,
  WaterloggingProperties
>;

// Historical affected-area polygons, not validated inundation boundaries.
type HistoricalFloodCollection = FeatureCollection<Geometry>;

type NavigationTarget = {
  latitude: number;
  longitude: number;
  requestId: number;
};

// ============================================================
// 3. REUSABLE UI COMPONENTS
// ============================================================

function AttributeRow({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div
      style={{
        marginBottom: 8,
        fontSize: 13,
        overflowWrap: "anywhere",
        lineHeight: 1.5,
      }}
    >
      <strong>{label}:</strong>{" "}
      {value === null ||
      value === undefined ||
      value === ""
        ? "Unknown"
        : String(value)}
    </div>
  );
}

function Section({
  title,
  children,
  background = "#ffffff",
}: {
  title: string;
  children: ReactNode;
  background?: string;
}) {
  return (
    <section
      style={{
        background,
        border: "1px solid #cbd5e1",
        borderRadius: 8,
        padding: 12,
        marginBottom: 14,
      }}
    >
      <h3
        style={{
          fontSize: 15,
          fontWeight: 700,
          margin: "0 0 12px",
          color: "#102a43",
        }}
      >
        {title}
      </h3>

      {children}
    </section>
  );
}

// ============================================================
// 4. PROXIMITY FORMATTING
// ============================================================

function formatRiverProximity(
  band?: string | null
): string {
  const labels: Record<string, string> = {
    intersects_mapped_water:
      "Intersects mapped river water",

    within_50m:
      "Within 50 metres",

    within_100m:
      "50–100 metres",

    within_250m:
      "100–250 metres",

    within_500m:
      "250–500 metres",

    beyond_500m:
      "Beyond 500 metres",
  };

  if (!band) {
    return "Unknown";
  }

  return labels[band] ?? band.replaceAll("_", " ");
}

function formatWaterloggingProximity(
  band?: string | null
): string {
  const labels: Record<string, string> = {
    contains_mapped_point:
      "Contains mapped location point",

    within_100m:
      "Within 100 metres",

    within_250m:
      "100–250 metres",

    within_500m:
      "250–500 metres",

    within_1000m:
      "500–1,000 metres",

    beyond_1000m:
      "Beyond 1,000 metres",
  };

  if (!band) {
    return "Unknown";
  }

  return labels[band] ?? band.replaceAll("_", " ");
}

// ============================================================
// 5. HEIGHT QUALITY BADGE
// ============================================================

function HeightQualityBadge({
  flag,
  height,
}: {
  flag?: HeightQualityFlag;
  height?: number | null;
}) {
  let label = "Model estimate — Unverified";

  let message =
    "Satellite-derived estimate. Not independently verified.";

  let background = "#eff6ff";
  let color = "#1d4ed8";

  if (
    height == null ||
    !Number.isFinite(height) ||
    height <= 0 ||
    flag === "unavailable"
  ) {
    label = "Height unavailable";

    message =
      "No usable estimate is available. " +
      "This does not mean the building has zero height.";

    background = "#f1f5f9";
    color = "#475569";
  } else if (
    flag === "review_low_estimate" ||
    height < 2
  ) {
    label = "Low estimate — Review required";

    message =
      "Estimated height is below 2 metres. " +
      "Further validation is required.";

    background = "#fff7ed";
    color = "#9a3412";
  }

  return (
    <div
      style={{
        padding: 10,
        margin: "10px 0",
        borderRadius: 6,
        background,
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      <strong style={{ color }}>{label}</strong>

      <p style={{ margin: "5px 0 0" }}>
        {message}
      </p>
    </div>
  );
}

// ============================================================
// 6. SOURCE INVESTIGATION
// ============================================================

function SourceInvestigationPanel({
  report,
}: {
  report: SourceInvestigationReport;
}) {
  return (
    <Section title="Source Investigation">
      <div
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 12,
        }}
      >
        <div
          style={{
            flex: 1,
            background: "#dcfce7",
            padding: 10,
            borderRadius: 6,
            textAlign: "center",
          }}
        >
          <strong>{report.sources_checked}</strong>

          <div style={{ fontSize: 11 }}>
            Sources checked
          </div>
        </div>

        <div
          style={{
            flex: 1,
            background: "#f1f5f9",
            padding: 10,
            borderRadius: 6,
            textAlign: "center",
          }}
        >
          <strong>{report.sources_pending}</strong>

          <div style={{ fontSize: 11 }}>
            Not yet searched
          </div>
        </div>
      </div>

      {report.investigations.map((item, index) => {
        const completed = item.status === "completed";

        return (
          <div
            key={`${item.source}-${index}`}
            style={{
              padding: 10,
              marginBottom: 8,
              borderRadius: 6,
              border: "1px solid #e2e8f0",
              background: completed
                ? "#f0fdf4"
                : "#f8fafc",
              fontSize: 12,
            }}
          >
            <strong>{item.source}</strong>

            <p
              style={{
                color: completed
                  ? "#15803d"
                  : "#64748b",
                margin: "5px 0",
              }}
            >
              {completed
                ? "✓ Data checked"
                : item.status === "not_searched"
                  ? "○ Not yet searched"
                  : item.status.replaceAll("_", " ")}
            </p>

            {item.access_method && (
              <AttributeRow
                label="Access"
                value={item.access_method}
              />
            )}

            {item.attributes_found &&
              Object.entries(
                item.attributes_found
              ).map(([key, value]) => (
                <div
                  key={key}
                  style={{
                    marginBottom: 4,
                    overflowWrap: "anywhere",
                  }}
                >
                  {key}: {String(value)}
                </div>
              ))}

            {item.attributes_missing &&
              item.attributes_missing.length > 0 && (
                <p style={{ color: "#b45309" }}>
                  <strong>Missing:</strong>{" "}
                  {item.attributes_missing.join(", ")}
                </p>
              )}

            {item.dataset_year && (
              <AttributeRow
                label="Dataset year"
                value={item.dataset_year}
              />
            )}

            {item.verification && (
              <AttributeRow
                label="Verification"
                value={item.verification}
              />
            )}

            {item.source_timestamp && (
              <AttributeRow
                label="Source updated"
                value={item.source_timestamp}
              />
            )}
          </div>
        );
      })}

      <p
        style={{
          fontSize: 11,
          color: "#64748b",
          lineHeight: 1.5,
        }}
      >
        Results use locally imported datasets.
        Sources marked not searched have not
        been queried automatically.
      </p>
    </Section>
  );
}

// ============================================================
// 7. MUSI RIVER PROXIMITY
// ============================================================

function MusiRiverPanel({
  building,
}: {
  building: BuildingResult;
}) {
  const distance =
    building.distance_to_musi_water_m;

  const evidence =
    building.attribute_evidence?.river_distance;

  return (
    <Section
      title="Musi River Proximity Intelligence"
      background="#ecfeff"
    >
      <div
        style={{
          fontSize: 26,
          color: "#0e7490",
          fontWeight: 700,
          marginBottom: 10,
        }}
      >
        {distance != null &&
        Number.isFinite(distance)
          ? `${distance.toFixed(2)} m`
          : "Unknown"}
      </div>

      <AttributeRow
        label="Proximity category"
        value={formatRiverProximity(
          building.river_proximity_band
        )}
      />

      <AttributeRow
        label="Mapped water intersection"
        value={
          building.intersects_mapped_water == null
            ? "Unknown"
            : building.intersects_mapped_water
              ? "Yes"
              : "No"
        }
      />

      <AttributeRow
        label="Data source"
        value={
          building.river_source ??
          evidence?.source
        }
      />

      <AttributeRow
        label="Geometry"
        value={evidence?.river_geometry_type}
      />

      <AttributeRow
        label="Calculation method"
        value={
          building.river_distance_method ??
          evidence?.calculation_method
        }
      />

      <AttributeRow
        label="Verification"
        value={
          building.river_verification ??
          evidence?.verification_status
        }
      />

      <AttributeRow
        label="River geometry IDs"
        value={evidence?.river_geometry_ids}
      />

      <div
        style={{
          marginTop: 12,
          padding: 10,
          borderRadius: 6,
          background: "#fff7ed",
          border: "1px solid #fdba74",
          fontSize: 12,
          color: "#9a3412",
          lineHeight: 1.6,
        }}
      >
        <strong>
          Geographic proximity only — not a flood-risk score
        </strong>

        <p style={{ margin: "5px 0 0" }}>
          The distance is calculated from the building
          footprint to mapped OpenStreetMap river-water
          polygons. It does not establish historical flooding
          or current inundation.
        </p>
      </div>
    </Section>
  );
}

// ============================================================
// 8. GOVERNMENT WATERLOGGING PROXIMITY — NEW
// ============================================================

function WaterloggingProximityPanel({
  building,
}: {
  building: BuildingResult;
}) {
  const distance =
    building.distance_to_waterlogging_point_m;

  const evidence =
    building.attribute_evidence?.waterlogging_distance;

  const hasDistance =
    distance != null &&
    Number.isFinite(distance);

  return (
    <Section
      title="Government Waterlogging Proximity Intelligence"
      background="#f5f3ff"
    >
      {/* DISTANCE */}

      <div
        style={{
          fontSize: 26,
          color: "#6d28d9",
          fontWeight: 700,
          marginBottom: 10,
        }}
      >
        {hasDistance
          ? `${distance.toFixed(2)} m`
          : "Unknown"}
      </div>

      {/* LOCATION */}

      <AttributeRow
        label="Nearest mapped location"
        value={
          building.nearest_waterlogging_location
        }
      />

      <AttributeRow
        label="Government record ID"
        value={
          building.nearest_waterlogging_id
        }
      />

      {/* PROXIMITY */}

      <AttributeRow
        label="Proximity category"
        value={formatWaterloggingProximity(
          building.waterlogging_proximity_band
        )}
      />

      {/* EVIDENCE */}

      <AttributeRow
        label="Data source"
        value={
          building.waterlogging_source ??
          evidence?.source
        }
      />

      <AttributeRow
        label="Geometry type"
        value={evidence?.geometry_type}
      />

      <AttributeRow
        label="Calculation method"
        value={
          building.waterlogging_distance_method ??
          evidence?.calculation_method
        }
      />

      <AttributeRow
        label="Verification"
        value={
          building.waterlogging_verification ??
          evidence?.verification_status
        }
      />

      <AttributeRow
        label="Observation date"
        value={
          evidence?.observation_date ??
          "Not available"
        }
      />

      <AttributeRow
        label="Water depth"
        value={
          evidence?.water_depth_m != null
            ? `${evidence.water_depth_m} m`
            : "Not available"
        }
      />

      <AttributeRow
        label="Confidence"
        value={
          evidence?.confidence ??
          "Not available"
        }
      />

      {/* EVIDENCE INTERPRETATION */}

      <div
        style={{
          marginTop: 12,
          padding: 10,
          borderRadius: 6,
          background: "#fff7ed",
          border: "1px solid #fdba74",
          color: "#9a3412",
          fontSize: 12,
          lineHeight: 1.6,
        }}
      >
        <strong>
          Government-mapped location — flooding not established
        </strong>

        <p style={{ margin: "6px 0 0" }}>
          This value represents the shortest approximate
          distance from the selected building footprint
          to the nearest location in the Telangana Government
          TGRAC waterlogging-point dataset.
        </p>

        <p style={{ margin: "6px 0 0" }}>
          The dataset contains 23 mapped locations.
          Observation dates, inundation boundaries,
          and water depths are unavailable.
          A nearby point does not confirm that this
          building experienced flooding.
        </p>
      </div>

      <div
        style={{
          marginTop: 10,
          padding: 8,
          borderRadius: 6,
          background: "#ede9fe",
          fontSize: 11,
          color: "#5b21b6",
        }}
      >
        <strong>Evidence classification:</strong>{" "}
        Geographic proximity to a government-mapped
        waterlogging point.
      </div>
    </Section>
  );
}

// ============================================================
// HISTORICAL FLOOD-AFFECTED AREA OVERLAP (OCTOBER 2020)
// ============================================================

function HistoricalFloodEvidencePanel({
  building,
}: {
  building: BuildingResult;
}) {
  const evidence = building.attribute_evidence?.historical_flood_area_overlap;
  const percentage = building.historical_polygon_overlap_pct ?? evidence?.value;
  const percentageLabel =
    percentage != null && Number.isFinite(percentage)
      ? `${percentage.toFixed(2)}%`
      : "Unavailable";
  const overlapCategory =
    building.historical_polygon_overlap_category ?? evidence?.overlap_category;
  const overlapArea =
    building.historical_polygon_overlap_m2 ?? evidence?.overlap_area_m2;

  return (
    <Section
      title="Historical Flood-Affected Area — October 2020"
      background="#fff7ed"
    >
      <div
        style={{
          fontSize: 26,
          color: "#9a3412",
          fontWeight: 700,
          marginBottom: 10,
        }}
      >
        {percentageLabel}
      </div>
      <AttributeRow label="Mapped-area overlap" value={overlapCategory} />
      <AttributeRow
        label="Footprint overlap area"
        value={overlapArea != null ? `${overlapArea.toFixed(2)} m²` : null}
      />
      <AttributeRow
        label="Evidence source"
        value={building.historical_polygon_source ?? evidence?.source}
      />
      <AttributeRow
        label="Historical period"
        value={evidence?.historical_period ?? "October 2020"}
      />
      <AttributeRow
        label="Measurement"
        value={evidence?.measurement_type ?? "Geometric polygon intersection"}
      />
      <AttributeRow
        label="Verification status"
        value={evidence?.verification_status ??
          building.historical_polygon_evidence_status}
      />
      <AttributeRow label="Source geometry file" value={evidence?.source_geometry_file} />
      <div
        style={{
          padding: 10,
          background: "#ffedd5",
          border: "1px solid #fdba74",
          borderRadius: 6,
          fontSize: 12,
          lineHeight: 1.6,
          color: "#9a3412",
        }}
      >
        <strong>Mapped historical flood-area overlap — not confirmed inundation.</strong>
        <p style={{ margin: "6px 0 0" }}>
          This percentage measures the building footprint inside the pilot area
          that intersects published flood-affected-area polygons. It does not
          verify water entry, depth, damage, or present-day flood risk.
          A value of 0% means no overlap with this particular dataset; it does
          not establish that the building remained dry.
        </p>
      </div>
    </Section>
  );
}

// ============================================================
// 9. BUILDING INTELLIGENCE PANEL
// ============================================================

function BuildingPanel({
  result,
  loading,
}: {
  result: BuildingResult | null;
  loading: boolean;
}) {
  return (
    <aside
      style={{
        width: "30%",
        minWidth: 300,
        height: "100%",
        overflowY: "auto",
        padding: 14,
        boxSizing: "border-box",
        background: "#f8fafc",
        color: "#172033",
        borderLeft: "1px solid #cbd5e1",
      }}
    >
      <h2
        style={{
          fontSize: 18,
          fontWeight: 700,
          margin: "0 0 14px",
        }}
      >
        Building Intelligence
      </h2>

      {loading && (
        <p>Identifying building...</p>
      )}

      {!loading && !result && (
        <p style={{ fontSize: 13 }}>
          Click a building or location on the map.
        </p>
      )}

      {/* ERROR */}

      {result?.match_type === "error" && (
        <Section
          title="Query Error"
          background="#fef2f2"
        >
          <p>{result.message}</p>
        </Section>
      )}

      {/* NEARBY BUILDINGS */}

      {result?.match_type === "none" && (
        <>
          <Section
            title="No Exact Building Match"
            background="#fff7ed"
          >
            <p style={{ fontSize: 13 }}>
              {result.message}
            </p>

            <AttributeRow
              label="Search radius"
              value={`${result.search_radius_m ?? 100} m`}
            />

            <AttributeRow
              label="Nearby candidates"
              value={
                result.nearby_candidates?.length ?? 0
              }
            />
          </Section>

          {(result.nearby_candidates ?? []).map(
            (candidate, index) => (
              <Section
                key={candidate.building_id}
                title={`Nearby Candidate ${index + 1}`}
              >
                <AttributeRow
                  label="Building ID"
                  value={candidate.building_id}
                />

                <AttributeRow
                  label="Distance from click"
                  value={`${candidate.distance_m.toFixed(2)} m`}
                />

                <AttributeRow
                  label="Estimated height"
                  value={
                    candidate.estimated_height_m != null
                      ? `${candidate.estimated_height_m.toFixed(2)} m`
                      : null
                  }
                />

                <HeightQualityBadge
                  flag={candidate.height_quality_flag}
                  height={candidate.estimated_height_m}
                />

                <AttributeRow
                  label="Footprint area"
                  value={
                    candidate.footprint_area_m2 != null
                      ? `${candidate.footprint_area_m2.toFixed(2)} m²`
                      : null
                  }
                />

                <AttributeRow
                  label="Area verification"
                  value={
                    candidate.area_verification
                  }
                />

                <AttributeRow
                  label="Distance to Musi River"
                  value={
                    candidate.distance_to_musi_water_m != null
                      ? `${candidate.distance_to_musi_water_m.toFixed(2)} m`
                      : null
                  }
                />

                <AttributeRow
                  label="Nearest waterlogging location"
                  value={
                    candidate.nearest_waterlogging_location
                  }
                />

                <AttributeRow
                  label="Distance to waterlogging point"
                  value={
                    candidate.distance_to_waterlogging_point_m != null
                      ? `${candidate.distance_to_waterlogging_point_m.toFixed(2)} m`
                      : null
                  }
                />

                <AttributeRow
                  label="Historical mapped-area overlap"
                  value={
                    candidate.historical_polygon_overlap_pct != null
                      ? `${candidate.historical_polygon_overlap_pct.toFixed(2)}%`
                      : "Unavailable"
                  }
                />
                <AttributeRow
                  label="Historical overlap category"
                  value={candidate.historical_polygon_overlap_category}
                />
                <p style={{ fontSize: 11, color: "#92400e", lineHeight: 1.5 }}>
                  Historical overlap is geometric evidence only, not confirmed
                  building inundation.
                </p>

                <p
                  style={{
                    fontSize: 11,
                    color: "#92400e",
                  }}
                >
                  Nearby candidate only.
                  Neither river proximity nor waterlogging-point
                  proximity establishes flood risk.
                </p>
              </Section>
            )
          )}
        </>
      )}

      {/* EXACT BUILDING */}

      {result?.match_type === "exact" && (
        <>
          {/* IDENTIFICATION */}

          <Section title="Building Identification">
            <p
              style={{
                fontSize: 12,
                color: "#15803d",
                fontWeight: 700,
              }}
            >
              ✓ Exact polygon match
            </p>

            <AttributeRow
              label="Building ID"
              value={result.building_id}
            />

            <AttributeRow
              label="Building tag"
              value={result.building_type}
            />

            <AttributeRow
              label="Floors"
              value={result.building_levels}
            />

            <AttributeRow
              label="OSM height"
              value={result.height}
            />

            <AttributeRow
              label="Construction year"
              value={result.construction_date}
            />

            <AttributeRow
              label="Source"
              value={result.source}
            />

            <AttributeRow
              label="Source updated"
              value={result.source_timestamp}
            />

            {result.building_type === "yes" && (
              <p
                style={{
                  fontSize: 11,
                  color: "#64748b",
                }}
              >
                The OSM tag &quot;yes&quot; indicates a
                mapped building, not verified occupancy type.
              </p>
            )}
          </Section>

          {/* GOOGLE HEIGHT */}

          <Section
            title="Google Building Height Intelligence"
            background="#e8f4ff"
          >
            <div
              style={{
                fontSize: 26,
                color: "#1d4ed8",
                fontWeight: 700,
              }}
            >
              {result.estimated_height_m != null
                ? `${result.estimated_height_m.toFixed(2)} m`
                : "Unknown"}
            </div>

            <HeightQualityBadge
              flag={result.height_quality_flag}
              height={result.estimated_height_m}
            />

            <AttributeRow
              label="Source"
              value={result.height_estimate_source}
            />

            <AttributeRow
              label="Dataset year"
              value={result.height_estimate_year}
            />

            <AttributeRow
              label="Verification"
              value={result.height_verification}
            />

            <AttributeRow
              label="Sampling"
              value={result.height_sampling_method}
            />

            <AttributeRow
              label="Confidence"
              value={
                result.attribute_evidence
                  ?.estimated_height?.confidence ??
                "Not available"
              }
            />
          </Section>

          {/* FOOTPRINT AREA */}

          <Section
            title="Building Footprint Area"
            background="#f0fdf4"
          >
            <div
              style={{
                fontSize: 26,
                color: "#166534",
                fontWeight: 700,
                marginBottom: 10,
              }}
            >
              {result.footprint_area_m2 != null
                ? `${result.footprint_area_m2.toFixed(2)} m²`
                : "Unknown"}
            </div>

            <AttributeRow
              label="Source"
              value={result.area_source}
            />

            <AttributeRow
              label="Calculation method"
              value={result.area_method}
            />

            <AttributeRow
              label="Verification"
              value={result.area_verification}
            />

            <p
              style={{
                fontSize: 11,
                color: "#475569",
              }}
            >
              Geometry-derived footprint area.
              Not an officially surveyed property area
              or total floor area.
            </p>
          </Section>

          {/* RIVER PROXIMITY */}

          <MusiRiverPanel building={result} />

          {/* NEW WATERLOGGING PROXIMITY */}

          <WaterloggingProximityPanel
            building={result}
          />

          {/* HISTORICAL FLOOD-AFFECTED AREA EVIDENCE */}

          <HistoricalFloodEvidencePanel building={result} />

          {/* SOURCE INVESTIGATION */}

          {result.source_investigation && (
            <SourceInvestigationPanel
              report={result.source_investigation}
            />
          )}
        </>
      )}
    </aside>
  );
}

// ============================================================
// 10. MAP NAVIGATION
// ============================================================

function MapNavigation({
  target,
}: {
  target: NavigationTarget | null;
}) {
  const map = useMap();

  useEffect(() => {
    if (!target) {
      return;
    }

    map.flyTo(
      [target.latitude, target.longitude],
      19,
      {
        animate: true,
        duration: 1.5,
      }
    );
  }, [map, target]);

  return null;
}

// ============================================================
// 11. GOVERNMENT WATERLOGGING MARKERS
// ============================================================

function WaterloggingLayer({
  features,
  selectedId,
}: {
  features: WaterloggingFeature[];
  selectedId: number | null;
}) {
  return (
    <>
      {features.map((feature, index) => {
        const coordinates =
          feature.geometry.coordinates;

        if (
          coordinates.length < 2 ||
          !Number.isFinite(coordinates[0]) ||
          !Number.isFinite(coordinates[1])
        ) {
          return null;
        }

        const longitude = coordinates[0];
        const latitude = coordinates[1];

        const properties = feature.properties;

        const isSelected =
          selectedId !== null &&
          properties.waterlogging_id === selectedId;

        return (
          <CircleMarker
            key={`waterlogging-${
              properties.waterlogging_id ?? index
            }`}
            center={[latitude, longitude]}
            radius={isSelected ? 14 : 9}
            bubblingMouseEvents={false}
            pathOptions={{
              color: isSelected
                ? "#4c1d95"
                : "#6b21a8",
              fillColor: isSelected
                ? "#7c3aed"
                : "#a855f7",
              fillOpacity: 0.9,
              weight: isSelected ? 4 : 2,
            }}
          >
            <Tooltip
              direction="top"
              offset={[0, -10]}
              opacity={1}
            >
              <div
                style={{
                  fontSize: 12,
                  minWidth: 210,
                  maxWidth: 280,
                  lineHeight: 1.6,
                }}
              >
                <strong
                  style={{
                    color: "#6b21a8",
                    fontSize: 13,
                  }}
                >
                  Government Waterlogging Location
                </strong>

                <br />

                <strong>Location:</strong>{" "}
                {properties.name ?? "Unknown"}

                <br />

                <strong>Record ID:</strong>{" "}
                {properties.waterlogging_id ?? "Unknown"}

                <br />

                <strong>Source:</strong>{" "}
                {properties.source ??
                  "Telangana Government TGRAC"}

                <br />

                <strong>Observation date:</strong>{" "}
                {properties.observation_date ??
                  "Not available"}

                <br />

                <strong>Water depth:</strong>{" "}
                {properties.water_depth_m != null
                  ? `${properties.water_depth_m} m`
                  : "Not available"}

                <br />

                <strong>Building flooding:</strong>{" "}
                Not established

                <hr style={{ margin: "6px 0" }} />

                <span style={{ color: "#92400e" }}>
                  Mapped waterlogging location only.
                  Not a verified flood boundary.
                </span>
              </div>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

// ============================================================
// 12. MAP CLICK HANDLER
// ============================================================

function MapClickHandler({
  onResult,
  onLoading,
}: {
  onResult: (result: BuildingResult) => void;
  onLoading: (value: boolean) => void;
}) {
  const requestCounter = useRef(0);

  useMapEvents({
    async click(event) {
      const requestId =
        ++requestCounter.current;

      const { lat, lng } = event.latlng;

      onLoading(true);

      try {
        const response = await fetch(
          `${BUILDING_API}/building/query?lat=${lat}&lon=${lng}`
        );

        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        const data: BuildingResult =
          await response.json();

        if (
          requestId === requestCounter.current
        ) {
          onResult(data);
        }
      } catch (error) {
        console.error(error);

        if (
          requestId === requestCounter.current
        ) {
          onResult({
            match_type: "error",
            message:
              "Building Intelligence API is unavailable.",
          });
        }
      } finally {
        if (
          requestId === requestCounter.current
        ) {
          onLoading(false);
        }
      }
    },
  });

  return null;
}

// ============================================================
// 13. MAIN INTERACTIVE MAP
// ============================================================

export default function BuildingMap() {
  const [result, setResult] =
    useState<BuildingResult | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [showWaterlogging, setShowWaterlogging] =
    useState(false);

  const [showHistoricalFlood, setShowHistoricalFlood] = useState(false);
  const [historicalFloodData, setHistoricalFloodData] =
    useState<HistoricalFloodCollection | null>(null);
  const [historicalFloodLoading, setHistoricalFloodLoading] = useState(false);
  const [historicalFloodError, setHistoricalFloodError] =
    useState<string | null>(null);

  const [waterloggingFeatures, setWaterloggingFeatures] =
    useState<WaterloggingFeature[]>([]);

  const [waterloggingLoading, setWaterloggingLoading] =
    useState(false);

  const [waterloggingError, setWaterloggingError] =
    useState<string | null>(null);

  const [selectedLocation, setSelectedLocation] =
    useState<string>("");

  const [navigationTarget, setNavigationTarget] =
    useState<NavigationTarget | null>(null);

  // Direct coordinate search and repeatable demo locations.
  const [searchLatitude, setSearchLatitude] = useState("17.36952195");
  const [searchLongitude, setSearchLongitude] = useState("78.51500170423367");
  const [demoLocation, setDemoLocation] = useState("");
  const [coordinateError, setCoordinateError] = useState<string | null>(null);
  const searchRequestCounter = useRef(0);

  const demoLocations = [
    {
      id: "mapped-area-overlap",
      label: "Demo 1 — Building with 100% mapped-area overlap",
      lat: 17.36952195,
      lon: 78.51500170423367,
    },
    {
      id: "malakpet-gunj",
      label: "Demo 2 — Malakpet Gunj waterlogging location",
      lat: 17.373301287,
      lon: 78.504616846,
    },
  ];

  async function navigateAndQuery(latitude: number, longitude: number) {
    if (
      !Number.isFinite(latitude) || !Number.isFinite(longitude) ||
      latitude < -90 || latitude > 90 ||
      longitude < -180 || longitude > 180
    ) {
      setCoordinateError("Enter a valid latitude (-90 to 90) and longitude (-180 to 180).");
      return;
    }

    setCoordinateError(null);
    setNavigationTarget({ latitude, longitude, requestId: Date.now() });
    const requestId = ++searchRequestCounter.current;
    setLoading(true);
    try {
      const response = await fetch(
        `${BUILDING_API}/building/query?lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}`
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data: BuildingResult = await response.json();
      if (requestId === searchRequestCounter.current) setResult(data);
    } catch (error) {
      console.error(error);
      if (requestId === searchRequestCounter.current) {
        setResult({
          match_type: "error",
          message: "Unable to query the selected coordinates. Check the building API on port 8000.",
        });
      }
    } finally {
      if (requestId === searchRequestCounter.current) setLoading(false);
    }
  }


  // ----------------------------------------------------------
  // LOAD HISTORICAL FLOOD-AFFECTED-AREA GEOMETRIES
  // ----------------------------------------------------------

  useEffect(() => {
    if (!showHistoricalFlood || historicalFloodData) return;

    const controller = new AbortController();

    async function loadHistoricalFlood() {
      setHistoricalFloodLoading(true);
      setHistoricalFloodError(null);
      try {
        const response = await fetch(HISTORICAL_FLOOD_GEOJSON_URL, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const payload: unknown = await response.json();
        if (
          !payload || typeof payload !== "object" ||
          !("type" in payload) || payload.type !== "FeatureCollection" ||
          !("features" in payload) || !Array.isArray(payload.features) ||
          payload.features.some(
            (feature: unknown) =>
              !feature || typeof feature !== "object" ||
              !("geometry" in feature) || !feature.geometry ||
              typeof feature.geometry !== "object" ||
              !("type" in feature.geometry) ||
              (feature.geometry.type !== "Polygon" &&
                feature.geometry.type !== "MultiPolygon")
          )
        ) {
          throw new Error("Invalid polygon GeoJSON FeatureCollection");
        }
        if (!controller.signal.aborted) {
          setHistoricalFloodData(payload as HistoricalFloodCollection);
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error("Historical flood GeoJSON error:", error);
        setHistoricalFloodError(
          "Unable to load the historical GeoJSON. Verify " +
          "/geojson/historical_flood_2020.geojson is accessible."
        );
      } finally {
        if (!controller.signal.aborted) setHistoricalFloodLoading(false);
      }
    }

    void loadHistoricalFlood();
    return () => controller.abort();
  }, [showHistoricalFlood, historicalFloodData]);

  // ----------------------------------------------------------
  // LOAD GOVERNMENT LOCATIONS
  // ----------------------------------------------------------

  useEffect(() => {
    if (!showWaterlogging) {
      return;
    }

    const controller = new AbortController();

    async function loadWaterlogging() {
      setWaterloggingLoading(true);
      setWaterloggingError(null);

      try {
        const response = await fetch(
          `${WATERLOGGING_API}/waterlogging/locations`,
          {
            signal: controller.signal,
          }
        );

        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        const data: WaterloggingCollection =
          await response.json();

        if (
          data.type !== "FeatureCollection" ||
          !Array.isArray(data.features)
        ) {
          throw new Error(
            "Invalid GeoJSON response"
          );
        }

        if (!controller.signal.aborted) {
          setWaterloggingFeatures(data.features);
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        console.error(error);

        setWaterloggingError(
          "Unable to load government waterlogging locations. " +
          "Check that the API on port 8001 is running."
        );
      } finally {
        if (!controller.signal.aborted) {
          setWaterloggingLoading(false);
        }
      }
    }

    loadWaterlogging();

    return () => {
      controller.abort();
    };
  }, [showWaterlogging]);

  // ----------------------------------------------------------
  // SORT LOCATIONS
  // ----------------------------------------------------------

  const sortedWaterloggingFeatures = [
    ...waterloggingFeatures,
  ].sort((a, b) =>
    (a.properties.name ?? "").localeCompare(
      b.properties.name ?? ""
    )
  );

  // ----------------------------------------------------------
  // AUTOMATIC NAVIGATION
  // ----------------------------------------------------------

  function goToSelectedLocation() {
    if (!selectedLocation) {
      return;
    }

    const feature = waterloggingFeatures.find(
      (item) =>
        String(item.properties.waterlogging_id) ===
        selectedLocation
    );

    if (!feature) {
      return;
    }

    const [longitude, latitude] =
      feature.geometry.coordinates;

    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude)
    ) {
      return;
    }

    setNavigationTarget({
      latitude,
      longitude,
      requestId: Date.now(),
    });
  }

  const selectedMarkerId =
    selectedLocation === ""
      ? null
      : Number(selectedLocation);

  // ----------------------------------------------------------
  // BUILDING GEOMETRIES
  // ----------------------------------------------------------

  const exactFeature: Feature<Geometry> | null =
    result?.match_type === "exact" &&
    result.geometry
      ? {
          type: "Feature",
          properties: {},
          geometry: result.geometry,
        }
      : null;

  const candidateFeatures: Feature<Geometry>[] =
    result?.match_type === "none"
      ? (result.nearby_candidates ?? [])
          .filter(
            (candidate) =>
              candidate.geometry !== undefined
          )
          .map((candidate) => ({
            type: "Feature",
            properties: {
              building_id: candidate.building_id,
            },
            geometry: candidate.geometry!,
          }))
      : [];

  // ----------------------------------------------------------
  // RENDER
  // ----------------------------------------------------------

  return (
    <div
      style={{
        display: "flex",
        width: "100%",
        height: "85vh",
      }}
    >
      {/* MAP AREA */}

      <div
        style={{
          width: "70%",
          height: "100%",
          position: "relative",
        }}
      >
        {/* GOVERNMENT DATA CONTROLS */}

        <div
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            zIndex: 1000,
            background: "#ffffff",
            border: "1px solid #cbd5e1",
            borderRadius: 8,
            padding: 12,
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
            width: 250,
            maxWidth: "calc(100% - 30px)",
            maxHeight: "calc(100% - 24px)",
            overflowY: "auto",
            color: "#172033",
          }}
        >
          {/* QUICK SEARCH: Coordinates or saved demonstration sites */}
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 7 }}>
            Find a Building
          </div>
          <label htmlFor="netra-demo" style={{ fontSize: 11, display: "block", marginBottom: 4 }}>
            Demo location
          </label>
          <select
            id="netra-demo"
            value={demoLocation}
            onChange={(event) => {
              const id = event.target.value;
              setDemoLocation(id);
              const location = demoLocations.find((item) => item.id === id);
              if (location) {
                setSearchLatitude(String(location.lat));
                setSearchLongitude(String(location.lon));
                void navigateAndQuery(location.lat, location.lon);
              }
            }}
            style={{ width: "100%", padding: 7, borderRadius: 5, border: "1px solid #cbd5e1", background: "white", color: "#172033", fontSize: 11 }}
          >
            <option value="">-- Select demo location --</option>
            {demoLocations.map((location) => (
              <option key={location.id} value={location.id}>{location.label}</option>
            ))}
          </select>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void navigateAndQuery(Number(searchLatitude), Number(searchLongitude));
            }}
            style={{ marginTop: 10 }}
          >
            <div style={{ display: "flex", gap: 6 }}>
              <label style={{ flex: 1, minWidth: 0, fontSize: 11 }}>
                Latitude
                <input
                  aria-label="Latitude"
                  type="number"
                  step="any"
                  required
                  value={searchLatitude}
                  onChange={(event) => {
                    setDemoLocation("");
                    setSearchLatitude(event.target.value);
                  }}
                  style={{ width: "100%", boxSizing: "border-box", padding: 6, marginTop: 4, border: "1px solid #cbd5e1", borderRadius: 5, color: "#172033", background: "white" }}
                />
              </label>
              <label style={{ flex: 1, minWidth: 0, fontSize: 11 }}>
                Longitude
                <input
                  aria-label="Longitude"
                  type="number"
                  step="any"
                  required
                  value={searchLongitude}
                  onChange={(event) => {
                    setDemoLocation("");
                    setSearchLongitude(event.target.value);
                  }}
                  style={{ width: "100%", boxSizing: "border-box", padding: 6, marginTop: 4, border: "1px solid #cbd5e1", borderRadius: 5, color: "#172033", background: "white" }}
                />
              </label>
            </div>
            <button
              type="submit"
              style={{ width: "100%", marginTop: 8, padding: "9px 12px", border: "none", borderRadius: 6, background: "#0e7490", color: "white", fontWeight: 700, fontSize: 12, cursor: "pointer" }}
            >
              Go to Coordinates &amp; Identify Building
            </button>
          </form>
          {coordinateError && (
            <p role="alert" style={{ color: "#b91c1c", fontSize: 11, marginBottom: 0 }}>
              {coordinateError}
            </p>
          )}
          <p style={{ fontSize: 10, lineHeight: 1.4, color: "#64748b", margin: "7px 0 12px" }}>
            Demo 1 shows mapped-area overlap, not confirmed building flooding.
          </p>
          <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: 12 }} />
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
            Historical Data Layers
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={showHistoricalFlood}
              onChange={(event) => setShowHistoricalFlood(event.target.checked)}
            />
            <span>Historical Flood-Affected Areas (2020)</span>
          </label>
          {showHistoricalFlood && (
            <div style={{ fontSize: 11, marginTop: 7, lineHeight: 1.5 }}>
              {historicalFloodLoading
                ? "Loading historical polygons..."
                : historicalFloodError
                  ? <span role="alert" style={{ color: "#b91c1c" }}>{historicalFloodError}</span>
                  : `${historicalFloodData?.features.length ?? 0} mapped polygons loaded`}
              <p style={{ color: "#075985", margin: "6px 0 0" }}>
                Blue overlay: published October 2020 flood-affected areas.
                Not verified building inundation or current flood risk.
              </p>
              <p style={{ color: "#64748b", margin: "5px 0 0" }}>
                Source: Hyderabad Floods 2020 SpatialMap. Polygons extend
                beyond the pilot boundary; one geometry was repaired.
              </p>
            </div>
          )}

          <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: 12, marginTop: 12 }} />
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              marginBottom: 10,
            }}
          >
            Government Data Layers
          </div>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={showWaterlogging}
              onChange={(event) => {
                const enabled =
                  event.target.checked;

                setShowWaterlogging(enabled);

                if (!enabled) {
                  setSelectedLocation("");
                  setNavigationTarget(null);
                }
              }}
            />

            <span>
              Waterlogging Locations
            </span>
          </label>

          {showWaterlogging && (
            <>
              <div
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  color: "#475569",
                }}
              >
                {waterloggingLoading
                  ? "Loading locations..."
                  : waterloggingError
                    ? waterloggingError
                    : `${waterloggingFeatures.length} government locations loaded`}
              </div>

              {/* LOCATION DROPDOWN */}

              <div style={{ marginTop: 12 }}>
                <label
                  htmlFor="waterlogging-location"
                  style={{
                    display: "block",
                    fontSize: 12,
                    fontWeight: 700,
                    marginBottom: 6,
                  }}
                >
                  Select Location
                </label>

                <select
                  id="waterlogging-location"
                  value={selectedLocation}
                  onChange={(event) =>
                    setSelectedLocation(
                      event.target.value
                    )
                  }
                  disabled={
                    waterloggingLoading ||
                    waterloggingFeatures.length === 0
                  }
                  style={{
                    width: "100%",
                    padding: 8,
                    border: "1px solid #cbd5e1",
                    borderRadius: 5,
                    background: "#ffffff",
                    color: "#172033",
                    fontSize: 12,
                  }}
                >
                  <option value="">
                    -- Choose a location --
                  </option>

                  {sortedWaterloggingFeatures.map(
                    (feature) => (
                      <option
                        key={
                          feature.properties
                            .waterlogging_id
                        }
                        value={String(
                          feature.properties
                            .waterlogging_id
                        )}
                      >
                        {feature.properties.name ??
                          "Unnamed location"}
                      </option>
                    )
                  )}
                </select>
              </div>

              {/* NAVIGATION BUTTON */}

              <button
                type="button"
                onClick={goToSelectedLocation}
                disabled={!selectedLocation}
                style={{
                  width: "100%",
                  marginTop: 10,
                  padding: "9px 12px",
                  border: "none",
                  borderRadius: 6,
                  background: selectedLocation
                    ? "#6d28d9"
                    : "#cbd5e1",
                  color: selectedLocation
                    ? "#ffffff"
                    : "#475569",
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: selectedLocation
                    ? "pointer"
                    : "not-allowed",
                }}
              >
                📍 Go to Location
              </button>
            </>
          )}

          <div
            style={{
              marginTop: 10,
              fontSize: 10,
              color: "#64748b",
              lineHeight: 1.5,
            }}
          >
            Source: Telangana Government TGRAC.
            Observation dates unavailable.
          </div>
        </div>

        {/* LEAFLET MAP */}

        <MapContainer
          center={DEFAULT_CENTER}
          zoom={18}
          maxZoom={21}
          style={{
            width: "100%",
            height: "100%",
          }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxNativeZoom={19}
            maxZoom={21}
          />

          {/* MAP NAVIGATION */}

          <MapNavigation
            target={navigationTarget}
          />

          {/* BUILDING IDENTIFICATION */}

          <MapClickHandler
            onResult={setResult}
            onLoading={setLoading}
          />

          {/* HISTORICAL FLOOD-AFFECTED POLYGONS — BLUE */}
          {/* Render below selected buildings; disable polygon mouse events
              so building queries work even when this layer is visible. */}
          {showHistoricalFlood && historicalFloodData && (
            <GeoJSON
              key="historical-flood-2020"
              data={historicalFloodData}
              interactive={false}
              style={{
                color: "#0369a1",
                weight: 2,
                fillColor: "#38bdf8",
                fillOpacity: 0.22,
              }}
            />
          )}

          {/* GOVERNMENT WATERLOGGING MARKERS */}

          {showWaterlogging &&
            waterloggingFeatures.length > 0 && (
              <WaterloggingLayer
                features={waterloggingFeatures}
                selectedId={selectedMarkerId}
              />
            )}

          {/* EXACT BUILDING — RED */}

          {exactFeature && (
            <GeoJSON
              key={`exact-${result?.building_id}`}
              data={exactFeature}
              style={{
                color: "#ef4444",
                weight: 3,
                fillColor: "#ef4444",
                fillOpacity: 0.45,
              }}
            />
          )}

          {/* NEARBY BUILDINGS — ORANGE */}

          {candidateFeatures.map(
            (feature, index) => (
              <GeoJSON
                key={`candidate-${index}-${feature.properties?.building_id}`}
                data={feature}
                style={{
                  color: "#f97316",
                  weight: 3,
                  fillColor: "#fb923c",
                  fillOpacity: 0.35,
                }}
              />
            )
          )}

          {/* CLICKED LOCATION — BLUE */}

          {result?.match_type === "none" &&
            result.latitude !== undefined &&
            result.longitude !== undefined && (
              <CircleMarker
                center={[
                  result.latitude,
                  result.longitude,
                ]}
                radius={6}
                pathOptions={{
                  color: "#1d4ed8",
                  fillColor: "#2563eb",
                  fillOpacity: 1,
                  weight: 2,
                }}
              />
            )}
        </MapContainer>
      </div>

      {/* BUILDING INTELLIGENCE PANEL */}

      <BuildingPanel
        result={result}
        loading={loading}
      />
    </div>
  );
}