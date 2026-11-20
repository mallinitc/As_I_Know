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

// Synthetically reported incidents at distinct real OSM building locations.
// Geographic building matches are real; every emergency measurement is fictional.
type SyntheticMapIncident = {
  scenario_id: string;
  building_id: string;
  synthetic: true;
  verification_status: "unverified";
  reported_people: number;
  reported_children: number;
  reported_seniors: number;
  reported_water_depth_m: number;
  reported_flow_velocity_mps: number;
  triage_status: string;
  rescue_priority: "not_assessed";
  location: {
    latitude: number;
    longitude: number;
    location_source: string;
  };
};

type SyntheticMapDataset = {
  assessment_type: "synthetic_multi_location_incident_comparison";
  ranking_performed: false;
  automated_dispatch_authorized: false;
  incidents: SyntheticMapIncident[];
};

function validSyntheticIncident(value: unknown): value is SyntheticMapIncident {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<SyntheticMapIncident>;
  const point = row.location;
  return (
    typeof row.scenario_id === "string" && row.scenario_id.length > 0 &&
    typeof row.building_id === "string" && row.building_id.length > 0 &&
    row.synthetic === true && row.verification_status === "unverified" &&
    row.rescue_priority === "not_assessed" &&
    !!point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude) &&
    point.latitude >= -90 && point.latitude <= 90 &&
    point.longitude >= -180 && point.longitude <= 180 &&
    [row.reported_people, row.reported_children, row.reported_seniors].every(
      (n) => typeof n === "number" && Number.isSafeInteger(n) && n >= 0
    ) &&
    row.reported_children! + row.reported_seniors! <= row.reported_people! &&
    [row.reported_water_depth_m, row.reported_flow_velocity_mps].every(
      (n) => typeof n === "number" && Number.isFinite(n) && n >= 0
    )
  );
}

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

  sentinel1_evidence_available?: boolean;
  sentinel1_historical_radar?: Sentinel1RadarEvidence;

  // Historical mapped flood-area intersection (not confirmed flooding)
  historical_polygon_overlap_pct?: number | null;
  historical_polygon_overlap_category?: string | null;
  historical_polygon_has_overlap?: boolean | null;
  historical_polygon_evidence_status?: string | null;
  generic_flood_area_overlap_pct?: number | null;
  named_locality_overlap_pct?: number | null;
  generic_flood_area_overlap_m2?: number | null;
  named_locality_overlap_m2?: number | null;
  historical_evidence_category?: string | null;
  building_inundation_status?: string | null;
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

type HistoricalCategoryEvidence = {
  source?: string | null;
  source_file?: string | null;
  source_geometry_file?: string | null;
  historical_period?: string | null;
  measurement_type?: string | null;
  verification_status?: string | null;
  historical_evidence_category?: string | null;
  generic_flood_area_overlap_pct?: number | null;
  named_locality_overlap_pct?: number | null;
  building_inundation_status?: string | null;
  note?: string | null;
};

// Historical Sentinel-1 radar evidence: exploratory measurements only.
type Sentinel1RadarEvidence = {
  availability?: "available" | "not_available" | string;
  source?: string | null;
  source_file?: string | null;
  verification_status?: string | null;
  measurement_type?: string | null;
  evidence_type?: string | null;
  flood_status?: string | null;
  building_inundation_status?: string | null;
  neighbourhood_radius_m?: number | null;
  proximity_group?: string | null;
  distance_m?: number | null;
  threshold_db?: number | null;
  control_start?: string | null;
  control_end?: string | null;
  event_start?: string | null;
  event_end?: string | null;
  control_VV_negative_fraction?: number | null;
  event_VV_negative_fraction?: number | null;
  control_VH_negative_fraction?: number | null;
  event_VH_negative_fraction?: number | null;
  control_VV_sample_count?: number | null;
  event_VV_sample_count?: number | null;
  control_VH_sample_count?: number | null;
  event_VH_sample_count?: number | null;
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
  generic_flood_area_overlap_pct?: number | null;
  named_locality_overlap_pct?: number | null;
  generic_flood_area_overlap_m2?: number | null;
  named_locality_overlap_m2?: number | null;
  historical_evidence_category?: string | null;
  building_inundation_status?: string | null;

  historical_flood_confirmed?: boolean;
  building_flooding_confirmed?: boolean;
  flood_risk_assigned?: boolean;

  // Satellite evidence (40 targeted experimental buildings only).
  sentinel1_evidence_available?: boolean;
  sentinel1_evidence_status?: string | null;
  sentinel1_historical_radar?: Sentinel1RadarEvidence;

  // Evidence
  attribute_evidence?: {
    estimated_height?: {
      confidence?: number | null;
    };

    river_distance?: RiverDistanceEvidence;

    waterlogging_distance?: WaterloggingDistanceEvidence;
    historical_flood_area_overlap?: HistoricalFloodAreaEvidence;
    historical_area_by_category?: HistoricalCategoryEvidence;
    sentinel1_historical_radar?: Sentinel1RadarEvidence;
  };

  geometry?: Geometry;

  source_investigation?: SourceInvestigationReport;

  nearby_candidates?: NearbyCandidate[];

  search_radius_m?: number;
};

// Unified evidence assessment and synthetic demo from FastAPI v0.10.0.
type AssessmentCompletenessSection = {
  available_count: number;
  missing_count: number;
  total_fields: number;
};

type AssessmentQualityRecord = {
  section: string;
  field: string;
  available: boolean;
  classification: string;
  current_incident_evidence: boolean;
  independently_verified: boolean;
};

type UnifiedRescueAssessment = {
  project: string;
  schema_version: string;
  building_id: string;
  evidence_completeness: {
    building: AssessmentCompletenessSection;
    environmental: AssessmentCompletenessSection;
    incident: AssessmentCompletenessSection;
  };
  evidence_quality: {
    classifications: Record<string, number>;
    records: AssessmentQualityRecord[];
  };
  rescue_readiness: {
    incident_fields_available: string[];
    incident_fields_missing: { field: string; description: string }[];
    explanation: string;
  };
  assessment: {
    current_flooding_status: string;
    rescue_priority: string;
    priority_score: number | null;
    human_review_required: boolean;
    automated_dispatch_authorized: boolean;
    explanation: string;
  };
};

type SyntheticIncidentAssessment = {
  building_id: string;
  scenario: {
    scenario_id: string;
    scenario_type: string;
    synthetic: boolean;
    verification_status: string;
  };
  synthetic_incident: {
    reported_values: {
      estimated_people_stranded?: number | null;
      children?: number | null;
      senior_citizens?: number | null;
      observed_water_depth_m?: number | null;
      observed_flow_velocity_mps?: number | null;
      observation_source?: string | null;
      verification_status?: string | null;
    };
    reported_indicators: Array<{
      indicator: string;
      value: number;
      unit?: string;
      explanation: string;
    }>;
    limitations: string[];
  };
  assessment: {
    triage_status: string;
    human_attention_flag: boolean;
    rescue_priority: string;
    human_review_required: boolean;
    automated_dispatch_authorized: boolean;
    explanation: string;
  };
  disclaimer: string;
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
  const combined = building.attribute_evidence?.historical_flood_area_overlap;
  const categoryEvidence = building.attribute_evidence?.historical_area_by_category;
  const combinedPct = building.historical_polygon_overlap_pct ?? combined?.value;
  const genericPct = building.generic_flood_area_overlap_pct ?? categoryEvidence?.generic_flood_area_overlap_pct;
  const localityPct = building.named_locality_overlap_pct ?? categoryEvidence?.named_locality_overlap_pct;
  const category = building.historical_evidence_category ?? categoryEvidence?.historical_evidence_category;
  const categoryNames: Record<string, string> = {
    no_overlap: "No overlap with either mapped category",
    generic_only: "Generic flood-affected-area polygon only",
    locality_only: "Named affected locality only",
    both: "Both mapped categories",
    unavailable: "Classification unavailable",
  };
  const formatPct = (value: number | null | undefined) =>
    value != null && Number.isFinite(value) ? `${value.toFixed(2)}%` : "Unavailable";

  return (
    <Section title="Historical Mapped-Area Evidence — October 2020" background="#fff7ed">
      <div style={{ fontSize: 11, fontWeight: 700, color: "#9a3412", marginBottom: 5 }}>
        Combined mapped-area coverage (legacy metric)
      </div>
      <div style={{ fontSize: 26, color: "#9a3412", fontWeight: 700, marginBottom: 10 }}>
        {formatPct(combinedPct)}
      </div>
      <div style={{ background: "#ffffff", padding: 10, borderRadius: 6, marginBottom: 10, border: "1px solid #fed7aa" }}>
        <AttributeRow label="Generic flood-affected-area polygon (SymbolID 0)" value={formatPct(genericPct)} />
        <AttributeRow label="Named affected locality (SymbolID 3)" value={formatPct(localityPct)} />
        <AttributeRow label="Category" value={category ? (categoryNames[category] ?? category) : "Unavailable"} />
        <AttributeRow label="Building inundation" value="Not established" />
      </div>
      <AttributeRow label="Combined overlap area" value={
        building.historical_polygon_overlap_m2 != null
          ? `${building.historical_polygon_overlap_m2.toFixed(2)} m²`
          : combined?.overlap_area_m2 != null
            ? `${combined.overlap_area_m2.toFixed(2)} m²`
            : null
      } />
      <AttributeRow label="Evidence source" value={building.historical_polygon_source ?? combined?.source} />
      <AttributeRow label="Historical period" value={categoryEvidence?.historical_period ?? "October 2020"} />
      <AttributeRow label="Category-specific evidence file" value={categoryEvidence?.source_file} />
      <AttributeRow label="Geometry file" value={categoryEvidence?.source_geometry_file ?? combined?.source_geometry_file} />
      <AttributeRow label="Verification" value={categoryEvidence?.verification_status ?? combined?.verification_status} />
      <div style={{ padding: 10, background: "#ffedd5", border: "1px solid #fdba74", borderRadius: 6, fontSize: 12, lineHeight: 1.6, color: "#9a3412" }}>
        <strong>Mapped-area coverage is not confirmed flooding.</strong>
        <p style={{ margin: "6px 0 0" }}>
          The combined percentage includes broad named-locality polygons and must not be interpreted
          as a flooded-building percentage. Neither category independently verifies water entry,
          floodwater depth, damage, or current flood risk. A 0% value does not prove a building stayed dry.
          Percentages are calculated for the building footprint clipped to the pilot area.
        </p>
      </div>
    </Section>
  );
}

// ============================================================
// HISTORICAL SENTINEL-1 RADAR EVIDENCE (EXPLORATORY)
// ============================================================

function Sentinel1RadarPanel({
  evidence,
}: {
  evidence?: Sentinel1RadarEvidence | null;
}) {
  const available = evidence?.availability === "available";

  const pct = (fraction: number | null | undefined): string =>
    typeof fraction === "number" && Number.isFinite(fraction)
      ? `${(fraction * 100).toFixed(2)}%`
      : "Unavailable";

  const period = (start?: string | null, end?: string | null): string =>
    start && end ? `${start} → ${end}` : "Unavailable";

  const groupLabel: Record<string, string> = {
    intersecting: "Intersects historical generic affected-area polygon",
    within_50m: "Within 50 m of historical generic affected-area polygon",
    "100_to_200m": "100–200 m from historical generic affected-area polygon",
  };

  return (
    <Section title="Sentinel-1 Historical Radar Evidence" background="#eff6ff">
      <div
        style={{
          display: "inline-block",
          padding: "5px 9px",
          borderRadius: 6,
          marginBottom: 12,
          fontSize: 12,
          fontWeight: 700,
          color: available ? "#1d4ed8" : "#475569",
          background: available ? "#dbeafe" : "#e2e8f0",
        }}
      >
        {available ? "Historical measurements available" : "No building-linked radar record"}
      </div>

      {!available ? (
        <p style={{ fontSize: 12, lineHeight: 1.6, margin: "0 0 10px" }}>
          This building is not among the 40 buildings included in the targeted
          satellite experiment. Missing radar evidence is not evidence of no flooding.
        </p>
      ) : (
        <>
          <AttributeRow
            label="Historical proximity group"
            value={evidence.proximity_group
              ? (groupLabel[evidence.proximity_group] ?? evidence.proximity_group)
              : "Unknown"}
          />
          <AttributeRow
            label="Distance to mapped generic area"
            value={evidence.distance_m != null
              ? `${evidence.distance_m.toFixed(2)} m`
              : null}
          />
          <AttributeRow
            label="Neighbourhood radius"
            value={evidence.neighbourhood_radius_m != null
              ? `${evidence.neighbourhood_radius_m} m`
              : null}
          />
          <AttributeRow label="Control acquisitions" value={period(evidence.control_start, evidence.control_end)} />
          <AttributeRow label="Event acquisitions" value={period(evidence.event_start, evidence.event_end)} />

          <div style={{ overflowX: "auto", margin: "12px 0" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "#dbeafe", color: "#1e3a8a" }}>
                  <th style={{ textAlign: "left", padding: 7 }}>Radar decrease &gt;3 dB</th>
                  <th style={{ textAlign: "right", padding: 7 }}>Control</th>
                  <th style={{ textAlign: "right", padding: 7 }}>Event</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ background: "#ffffff" }}>
                  <th scope="row" style={{ textAlign: "left", padding: 7 }}>VV</th>
                  <td style={{ textAlign: "right", padding: 7 }}>{pct(evidence.control_VV_negative_fraction)}</td>
                  <td style={{ textAlign: "right", padding: 7, fontWeight: 700 }}>{pct(evidence.event_VV_negative_fraction)}</td>
                </tr>
                <tr style={{ background: "#f8fafc" }}>
                  <th scope="row" style={{ textAlign: "left", padding: 7 }}>VH</th>
                  <td style={{ textAlign: "right", padding: 7 }}>{pct(evidence.control_VH_negative_fraction)}</td>
                  <td style={{ textAlign: "right", padding: 7, fontWeight: 700 }}>{pct(evidence.event_VH_negative_fraction)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <AttributeRow label="Control VV / VH sample counts" value={
            `${evidence.control_VV_sample_count ?? "Unknown"} / ${evidence.control_VH_sample_count ?? "Unknown"}`
          } />
          <AttributeRow label="Event VV / VH sample counts" value={
            `${evidence.event_VV_sample_count ?? "Unknown"} / ${evidence.event_VH_sample_count ?? "Unknown"}`
          } />
        </>
      )}

      <AttributeRow label="Data source" value={evidence?.source ?? "Sentinel-1A / Google Earth Engine"} />
      <AttributeRow label="Source file" value={evidence?.source_file} />
      <AttributeRow label="Verification" value={evidence?.verification_status ?? "Unavailable"} />

      <div style={{ marginTop: 10, padding: 10, borderRadius: 6, border: "1px solid #fbbf24", background: "#fffbeb", color: "#92400e", fontSize: 12, lineHeight: 1.6 }}>
        <strong>Exploratory radar change — not verified flooding.</strong>
        <p style={{ margin: "6px 0 0" }}>
          Percentages indicate the share of sampled radar locations within a building-centred
          neighbourhood whose backscatter decreased by more than 3 dB. Raster samples are
          spatially dependent; nearby neighbourhoods may share samples. These historical
          observations do not confirm building inundation, water depth, current conditions,
          rescue urgency, or a flood probability.
        </p>
      </div>
    </Section>
  );
}

// ============================================================
// UNIFIED RESCUE ASSESSMENT (API v0.10.0, EXPERIMENTAL)
// ============================================================

const EVIDENCE_CATEGORY_LABELS: Record<string, string> = {
  geometry_derived: "Geometry-derived",
  model_estimated: "Model-estimated",
  mapped_historical: "Historical map evidence",
  observed_historical: "Historical radar observations",
  verified_current: "Verified current",
  unverified_current: "Unverified current",
  unavailable: "Unavailable",
  unclassified: "Unclassified",
};

function AssessmentCount({
  label,
  available,
  total,
}: {
  label: string;
  available: number;
  total: number;
}) {
  return (
    <div style={{ padding: 9, background: "#ffffff", border: "1px solid #dbeafe", borderRadius: 7 }}>
      <div style={{ fontSize: 11, color: "#475569" }}>{label}</div>
      <strong style={{ fontSize: 18, color: "#1e40af" }}>{available}/{total}</strong>
      <div style={{ fontSize: 10, color: "#64748b" }}>Populated fields (not a confidence score)</div>
    </div>
  );
}

function RescueAssessmentPanel({ building }: { building: BuildingResult }) {
  const [assessment, setAssessment] = useState<UnifiedRescueAssessment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetching, setFetching] = useState(true);
  const [demo, setDemo] = useState<SyntheticIncidentAssessment | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const demoRequest = useRef<AbortController | null>(null);
  const latitude = building.latitude;
  const longitude = building.longitude;
  const buildingId = building.building_id;

  useEffect(() => {
    const controller = new AbortController();
    setAssessment(null);
    setError(null);
    setFetching(true);

    if (latitude == null || longitude == null || !buildingId) {
      setError("Building coordinates unavailable for unified assessment.");
      setFetching(false);
      return () => controller.abort();
    }

    async function loadAssessment() {
      try {
        const url = `${BUILDING_API}/rescue/assessment?lat=${encodeURIComponent(latitude!)}&lon=${encodeURIComponent(longitude!)}`;
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload: UnifiedRescueAssessment = await response.json();
        if (payload.building_id !== buildingId || !payload.assessment ||
            !payload.evidence_completeness || !payload.evidence_quality || !payload.rescue_readiness) {
          throw new Error("Unexpected assessment response or building ID mismatch");
        }
        if (!controller.signal.aborted) setAssessment(payload);
      } catch (cause) {
        if (!controller.signal.aborted) {
          console.error("Unified rescue assessment failed:", cause);
          setError("Assessment unavailable. Check FastAPI v0.10.0 on port 8000.");
        }
      } finally {
        if (!controller.signal.aborted) setFetching(false);
      }
    }

    void loadAssessment();
    return () => controller.abort();
  }, [latitude, longitude, buildingId]);

  useEffect(() => {
    return () => demoRequest.current?.abort();
  }, []);

  async function loadSyntheticDemo() {
    demoRequest.current?.abort();
    const controller = new AbortController();
    demoRequest.current = controller;
    setDemoLoading(true);
    setDemoError(null);
    setDemo(null);
    try {
      const url = `${BUILDING_API}/rescue/demo-incident?scenario_id=AI_NETRA_DEMO_001`;
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload: SyntheticIncidentAssessment = await response.json();
      if (payload.building_id !== buildingId ||
          payload.scenario?.scenario_id !== "AI_NETRA_DEMO_001" ||
          payload.scenario?.synthetic !== true ||
          !payload.synthetic_incident?.reported_values ||
          !Array.isArray(payload.synthetic_incident?.reported_indicators) ||
          !payload.assessment ||
          payload.assessment.automated_dispatch_authorized !== false) {
        throw new Error("Invalid synthetic demo response or building mismatch");
      }
      if (!controller.signal.aborted) setDemo(payload);
    } catch (cause) {
      if (!controller.signal.aborted) {
        console.error("Synthetic demo assessment failed:", cause);
        setDemoError("Synthetic demo unavailable. Check FastAPI v0.10.0 on port 8000.");
      }
    } finally {
      if (!controller.signal.aborted) setDemoLoading(false);
    }
  }

  function closeSyntheticDemo() {
    demoRequest.current?.abort();
    setDemo(null);
    setDemoError(null);
    setDemoLoading(false);
  }

  const counts = assessment?.evidence_completeness;
  const categories = assessment?.evidence_quality.classifications ?? {};
  const missing = assessment?.rescue_readiness.incident_fields_missing ?? [];
  const reviewed = assessment?.evidence_quality.records.filter(
    (record) => record.classification === "verified_current"
  ).length ?? 0;

  return (
    <Section title="Unified Rescue Assessment — Experimental" background="#eff6ff">
      {buildingId === "osm-way-357584220" && (
        <div style={{ marginBottom: 12, padding: 10, border: "1px solid #f59e0b", borderRadius: 8, background: "#fffbeb" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 7 }}>
            SYNTHETIC TRAINING DEMO — NOT A REAL EMERGENCY
          </div>
          <button
            type="button"
            disabled={demoLoading}
            onClick={() => { if (demo) closeSyntheticDemo(); else void loadSyntheticDemo(); }}
            style={{ padding: "9px 12px", border: 0, borderRadius: 6, background: demo ? "#64748b" : "#b45309", color: "white", cursor: demoLoading ? "wait" : "pointer", fontWeight: 700 }}
          >
            {demoLoading ? "Loading synthetic incident..." : demo ? "Hide Demo Emergency Scenario" : "Show Demo Emergency Scenario"}
          </button>
          {demoError && <p role="alert" style={{ color: "#b91c1c", fontSize: 12 }}>{demoError}</p>}
          {demo && (
            <div style={{ marginTop: 12, padding: 11, background: "#ffffff", borderRadius: 7, border: "2px solid #f59e0b", fontSize: 12 }}>
              <h4 style={{ margin: "0 0 9px", color: "#92400e", fontSize: 14 }}>⚠ Simulated incident — {demo.scenario.scenario_id}</h4>
              <AttributeRow label="Scenario type" value="Synthetic / fictional / unverified" />
              <AttributeRow label="Reported people" value={demo.synthetic_incident.reported_values.estimated_people_stranded} />
              <AttributeRow label="Reported children" value={demo.synthetic_incident.reported_values.children} />
              <AttributeRow label="Reported seniors" value={demo.synthetic_incident.reported_values.senior_citizens} />
              <AttributeRow label="Reported water depth" value={demo.synthetic_incident.reported_values.observed_water_depth_m == null ? null : `${demo.synthetic_incident.reported_values.observed_water_depth_m} m (fictional)`} />
              <AttributeRow label="Reported flow velocity" value={demo.synthetic_incident.reported_values.observed_flow_velocity_mps == null ? null : `${demo.synthetic_incident.reported_values.observed_flow_velocity_mps} m/s (fictional)`} />
              <AttributeRow label="Triage status" value={demo.assessment.triage_status.replaceAll("_", " ")} />
              <AttributeRow label="Human attention" value={demo.assessment.human_attention_flag ? "Flagged for human review" : "Not flagged"} />
              <AttributeRow label="Rescue priority" value={demo.assessment.rescue_priority.replaceAll("_", " ")} />
              <AttributeRow label="Automated dispatch" value="Disabled" />
              <h4 style={{ fontSize: 12, margin: "12px 0 5px" }}>Reported indicators ({demo.synthetic_incident.reported_indicators.length})</h4>
              <ul style={{ paddingLeft: 17, lineHeight: 1.6, margin: "0 0 10px" }}>
                {demo.synthetic_incident.reported_indicators.map((indicator) => (
                  <li key={indicator.indicator}><strong>{indicator.indicator.replaceAll("_", " ")}</strong>: {indicator.value}{indicator.unit ? ` ${indicator.unit}` : ""}</li>
                ))}
              </ul>
              <p style={{ color: "#92400e", lineHeight: 1.6, fontWeight: 700 }}>{demo.disclaimer}</p>
              <p style={{ color: "#475569", lineHeight: 1.6 }}>{demo.assessment.explanation}</p>
              <p style={{ color: "#475569", lineHeight: 1.6, marginBottom: 0 }}>
                Live incident fields below remain unavailable. Synthetic inputs are isolated and do not establish actual flooding or an operational rescue decision.
              </p>
            </div>
          )}
        </div>
      )}
      {fetching && <p style={{ fontSize: 12 }}>Loading evidence assessment...</p>}
      {error && <p role="alert" style={{ fontSize: 12, color: "#b91c1c" }}>{error}</p>}
      {assessment && counts && (
        <>
          <p style={{ fontSize: 12, margin: "0 0 10px", color: "#334155", lineHeight: 1.5 }}>
            Evidence provenance and incident-readiness review for <strong>{assessment.building_id}</strong>.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginBottom: 12 }}>
            <AssessmentCount label="Building" available={counts.building.available_count} total={counts.building.total_fields} />
            <AssessmentCount label="Environmental" available={counts.environmental.available_count} total={counts.environmental.total_fields} />
            <AssessmentCount label="Incident metadata" available={counts.incident.available_count} total={counts.incident.total_fields} />
            <div style={{ padding: 9, background: "#ffffff", border: "1px solid #dbeafe", borderRadius: 7 }}>
              <div style={{ fontSize: 11, color: "#475569" }}>Verified current fields</div>
              <strong style={{ fontSize: 18, color: "#1e40af" }}>{reviewed}</strong>
              <div style={{ fontSize: 10, color: "#64748b" }}>Independent verification not inferred</div>
            </div>
          </div>
          <div style={{ padding: 10, background: "#ffffff", borderRadius: 7, border: "1px solid #dbeafe", marginBottom: 10 }}>
            <h4 style={{ fontSize: 12, margin: "0 0 8px", color: "#1e3a8a" }}>Evidence quality and provenance</h4>
            {Object.keys(categories).length === 0 ? (
              <p style={{ fontSize: 12, margin: 0 }}>No classifications returned.</p>
            ) : (
              Object.entries(categories).map(([category, count]) => (
                <div key={category} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, padding: "4px 0", borderBottom: "1px solid #f1f5f9" }}>
                  <span>{EVIDENCE_CATEGORY_LABELS[category] ?? category.replaceAll("_", " ")}</span>
                  <strong>{count}</strong>
                </div>
              ))
            )}
          </div>
          <div style={{ padding: 10, background: "#fff7ed", border: "1px solid #fdba74", borderRadius: 7, marginBottom: 10 }}>
            <h4 style={{ margin: "0 0 7px", fontSize: 12, color: "#9a3412" }}>Current incident evidence gaps</h4>
            {missing.length > 0 ? (
              <ul style={{ margin: "4px 0 8px", paddingLeft: 18, fontSize: 12, lineHeight: 1.7, color: "#78350f" }}>
                {missing.map((item) => <li key={item.field}>{item.description}</li>)}
              </ul>
            ) : (
              <p style={{ fontSize: 12, color: "#78350f" }}>No gaps reported. Human assessment is still required.</p>
            )}
            <p style={{ margin: 0, fontSize: 11, lineHeight: 1.5, color: "#92400e" }}>
              A populated verification-status field marked “unavailable” is not verified evidence.
              Missing measurements must not delay emergency response to credible reports.
            </p>
          </div>
          <div style={{ padding: 10, background: "#ffffff", borderRadius: 7, border: "1px solid #cbd5e1" }}>
            <AttributeRow label="Current flooding" value={assessment.assessment.current_flooding_status.replaceAll("_", " ")} />
            <AttributeRow label="Rescue priority" value={assessment.assessment.rescue_priority.replaceAll("_", " ")} />
            <AttributeRow label="Priority score" value={assessment.assessment.priority_score ?? "Not assigned"} />
            <AttributeRow label="Human review" value={assessment.assessment.human_review_required ? "Required" : "Not flagged"} />
            <AttributeRow label="Automated dispatch" value={assessment.assessment.automated_dispatch_authorized ? "Authorized" : "Disabled"} />
            <p style={{ fontSize: 12, lineHeight: 1.6, margin: "5px 0 0", color: "#334155" }}>
              {assessment.assessment.explanation}
            </p>
          </div>
          <p style={{ margin: "9px 0 0", fontSize: 11, color: "#92400e", lineHeight: 1.5 }}>
            Historical proximity, mapped-area overlap, and radar changes do not establish current flooding, occupant needs, or rescue urgency.
          </p>
        </>
      )}
    </Section>
  );
}

// ============================================================
// SYNTHETIC COORDINATION: SELECTED INCIDENT DETAILS
// ============================================================

function SelectedSyntheticIncidentPanel({
  incident,
}: {
  incident: SyntheticMapIncident;
}) {
  const indicators = [
    ["People reportedly stranded", String(incident.reported_people)],
    ["Children reportedly present", String(incident.reported_children)],
    ["Seniors reportedly present", String(incident.reported_seniors)],
    ["Reported water depth", `${incident.reported_water_depth_m} m`],
    ["Reported flow velocity", `${incident.reported_flow_velocity_mps} m/s`],
  ] as const;

  return (
    <Section title="Selected Incident — Synthetic Coordination" background="#fff7ed">
      <div style={{ border: "1px solid #f59e0b", background: "#ffedd5", color: "#9a3412", padding: 9, borderRadius: 6, fontSize: 12, fontWeight: 700, marginBottom: 11 }}>
        FICTIONAL TRAINING SCENARIO — NOT LIVE FLOODING
      </div>
      <AttributeRow label="Scenario" value={incident.scenario_id} />
      <AttributeRow label="Matched building" value={incident.building_id} />
      <AttributeRow label="Reported verification" value="Unverified (synthetic)" />
      <div style={{ borderTop: "1px solid #fed7aa", margin: "10px 0" }} />
      {indicators.map(([label, value]) => (
        <AttributeRow key={label} label={label} value={value} />
      ))}
      <div style={{ borderTop: "1px solid #fed7aa", margin: "10px 0" }} />
      <AttributeRow label="Triage status" value={incident.triage_status.replaceAll("_", " ")} />
      <AttributeRow label="Human review" value="Required for fictional reported assistance needs" />
      <AttributeRow label="Rescue priority" value="Not assessed" />
      <AttributeRow label="Automated dispatch" value="Disabled" />
      <p style={{ color: "#92400e", fontSize: 11, lineHeight: 1.6, marginBottom: 0 }}>
        Building geometry is mapped OSM data. All incident counts, depths and flow values are
        fictional and unverified. The human-attention indicator is not an operational ranking,
        flood confirmation, or dispatch authorization. The unified assessment below evaluates
        actual available evidence separately from these test inputs.
      </p>
    </Section>
  );
}

// ============================================================
// 9. BUILDING INTELLIGENCE PANEL
// ============================================================

function BuildingPanel({
  result,
  loading,
  selectedSyntheticIncident,
}: {
  result: BuildingResult | null;
  loading: boolean;
  selectedSyntheticIncident: SyntheticMapIncident | null;
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
                  label="Combined mapped-area coverage (legacy)"
                  value={candidate.historical_polygon_overlap_pct != null
                    ? `${candidate.historical_polygon_overlap_pct.toFixed(2)}%`
                    : "Unavailable"}
                />
                <AttributeRow
                  label="Generic flood-affected area (SymbolID 0)"
                  value={candidate.generic_flood_area_overlap_pct != null
                    ? `${candidate.generic_flood_area_overlap_pct.toFixed(2)}%`
                    : "Unavailable"}
                />
                <AttributeRow
                  label="Named affected locality (SymbolID 3)"
                  value={candidate.named_locality_overlap_pct != null
                    ? `${candidate.named_locality_overlap_pct.toFixed(2)}%`
                    : "Unavailable"}
                />
                <AttributeRow label="Historical evidence category" value={candidate.historical_evidence_category} />
                <AttributeRow label="Building inundation" value="Not established" />
                <AttributeRow
                  label="Sentinel-1 historical radar evidence"
                  value={candidate.sentinel1_historical_radar?.availability === "available"
                    ? "Available — select exact building to view"
                    : "Not available for this building"}
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
          {selectedSyntheticIncident && (
            <SelectedSyntheticIncidentPanel incident={selectedSyntheticIncident} />
          )}
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

          {/* UNIFIED RESCUE ASSESSMENT — LIVE API v0.10.0 */}
          <RescueAssessmentPanel key={result.building_id} building={result} />

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

          {/* HISTORICAL SENTINEL-1 EVIDENCE */}
          <Sentinel1RadarPanel
            evidence={result.attribute_evidence?.sentinel1_historical_radar ?? result.sentinel1_historical_radar}
          />

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
// SYNTHETIC MULTI-LOCATION EMERGENCY MARKERS (NOT LIVE EVENTS)
// ============================================================

function SyntheticIncidentLayer({
  incidents,
  selectedBuildingId,
  onSelect,
}: {
  incidents: SyntheticMapIncident[];
  selectedBuildingId?: string;
  onSelect: (incident: SyntheticMapIncident) => void;
}) {
  return (
    <>
      {incidents.map((incident) => {
        const selected = selectedBuildingId === incident.building_id;
        return (
          <CircleMarker
            key={`synthetic-${incident.scenario_id}`}
            center={[incident.location.latitude, incident.location.longitude]}
            radius={selected ? 13 : 10}
            bubblingMouseEvents={false}
            eventHandlers={{
              click: () => onSelect(incident),
            }}
            pathOptions={{
              color: selected ? "#7c2d12" : "#9a3412",
              fillColor: selected ? "#f97316" : "#fdba74",
              fillOpacity: 0.94,
              weight: selected ? 4 : 3,
            }}
          >
            <Tooltip direction="top" offset={[0, -10]} opacity={1}>
              <div style={{ minWidth: 225, maxWidth: 265, fontSize: 12, lineHeight: 1.55 }}>
                <strong style={{ color: "#9a3412" }}>SYNTHETIC DEMO — NOT A REAL EMERGENCY</strong>
                <div><strong>Scenario:</strong> {incident.scenario_id}</div>
                <div><strong>Mapped building:</strong> {incident.building_id}</div>
                <div><strong>Reported people:</strong> {incident.reported_people}</div>
                <div><strong>Children / seniors:</strong> {incident.reported_children} / {incident.reported_seniors}</div>
                <div><strong>Reported depth:</strong> {incident.reported_water_depth_m} m</div>
                <div><strong>Reported flow:</strong> {incident.reported_flow_velocity_mps} m/s</div>
                <div><strong>Verification:</strong> Unverified (fictional)</div>
                <div><strong>Rescue priority:</strong> Not assessed</div>
                <div style={{ color: "#92400e", marginTop: 5 }}>
                  Click marker to inspect its actual mapped building. All incident details are synthetic.
                </div>
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

  const [showSyntheticIncidents, setShowSyntheticIncidents] = useState(false);
  const [syntheticIncidents, setSyntheticIncidents] = useState<SyntheticMapIncident[]>([]);
  const [syntheticIncidentsLoading, setSyntheticIncidentsLoading] = useState(false);
  const [syntheticIncidentsError, setSyntheticIncidentsError] = useState<string | null>(null);

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
      id: "radar-and-rescue-assessment",
      label: "Demo — Sentinel-1 + Unified Rescue Assessment",
      lat: 17.37990065,
      lon: 78.51797466199042,
    },
    {
      id: "malakpet-gunj",
      label: "Demo 2 — Malakpet Gunj waterlogging location",
      lat: 17.373301287,
      lon: 78.504616846,
    },
  ];

  // The public demo dataset contains fictional observations. Do not substitute
  // it for current incident evidence in the live rescue-assessment endpoint.
  useEffect(() => {
    if (!showSyntheticIncidents) return;
    const controller = new AbortController();
    async function loadSyntheticIncidents() {
      setSyntheticIncidentsLoading(true);
      setSyntheticIncidentsError(null);
      try {
        const response = await fetch("/demo/multi_location_incidents_v1.json", {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload: unknown = await response.json();
        if (!payload || typeof payload !== "object") throw new Error("Invalid payload");
        const data = payload as Partial<SyntheticMapDataset>;
        if (
          data.assessment_type !== "synthetic_multi_location_incident_comparison" ||
          data.ranking_performed !== false ||
          data.automated_dispatch_authorized !== false ||
          !Array.isArray(data.incidents) || data.incidents.length !== 3 ||
          !data.incidents.every(validSyntheticIncident) ||
          new Set(data.incidents.map((item) => item.building_id)).size !== 3
        ) {
          throw new Error("Dataset failed synthetic-only validation");
        }
        if (!controller.signal.aborted) setSyntheticIncidents(data.incidents);
      } catch (cause) {
        if (!controller.signal.aborted) {
          console.error("Synthetic incident map dataset unavailable:", cause);
          setSyntheticIncidents([]);
          setSyntheticIncidentsError("Unable to load the 3 synthetic incidents. Check /demo/multi_location_incidents_v1.json.");
        }
      } finally {
        if (!controller.signal.aborted) setSyntheticIncidentsLoading(false);
      }
    }
    void loadSyntheticIncidents();
    return () => controller.abort();
  }, [showSyntheticIncidents]);

  function selectSyntheticIncident(incident: SyntheticMapIncident) {
    setDemoLocation("");
    setSearchLatitude(String(incident.location.latitude));
    setSearchLongitude(String(incident.location.longitude));
    void navigateAndQuery(incident.location.latitude, incident.location.longitude);
  }

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

  // Only associate a fictional report with a verified exact building match.
  // Manual navigation to a mapped demo building is also synchronized.
  const selectedSyntheticIncident =
    showSyntheticIncidents && result?.match_type === "exact"
      ? syntheticIncidents.find((incident) => incident.building_id === result.building_id) ?? null
      : null;

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
            Demo 1 shows 100% named-locality coverage, not confirmed building flooding.
          </p>
          <div style={{ borderTop: "1px solid #fed7aa", paddingTop: 10, marginTop: 10 }} />
          <div style={{ fontSize: 13, fontWeight: 700, color: "#9a3412", marginBottom: 7 }}>
            Synthetic Emergency Demo
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={showSyntheticIncidents}
              onChange={(event) => setShowSyntheticIncidents(event.target.checked)}
            />
            <span>Show 3 fictional incident markers</span>
          </label>
          {showSyntheticIncidents && (
            <div style={{ background: "#fff7ed", border: "1px solid #fdba74", padding: 9, marginTop: 8, borderRadius: 6, fontSize: 11, lineHeight: 1.5 }}>
              <strong style={{ color: "#9a3412" }}>SYNTHETIC ONLY — NOT LIVE FLOODING</strong>
              <div style={{ marginTop: 5 }}>
                {syntheticIncidentsLoading ? "Loading synthetic markers..." :
                  syntheticIncidentsError ? <span role="alert" style={{ color: "#b91c1c" }}>{syntheticIncidentsError}</span> :
                  `${syntheticIncidents.length} fictional incidents loaded. Select any orange marker to inspect its real building location.`}
              </div>
              <div style={{ marginTop: 5, color: "#92400e" }}>
                No ranking, verified current flooding, or automated dispatch.
              </div>
              {!syntheticIncidentsLoading && !syntheticIncidentsError && syntheticIncidents.length > 0 && (
                <div style={{ marginTop: 11 }}>
                  <strong style={{ color: "#7c2d12", display: "block", marginBottom: 6 }}>
                    Multi-Incident Coordination — Fictional Reports
                  </strong>
                  {syntheticIncidents.map((incident) => {
                    const selected = selectedSyntheticIncident?.scenario_id === incident.scenario_id;
                    return (
                      <button
                        key={incident.scenario_id}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => selectSyntheticIncident(incident)}
                        style={{
                          display: "block", width: "100%", textAlign: "left", marginTop: 6,
                          padding: "9px 8px", borderRadius: 6, cursor: "pointer",
                          background: selected ? "#ffedd5" : "#ffffff",
                          border: selected ? "2px solid #c2410c" : "1px solid #fdba74",
                          color: "#431407", fontSize: 11, lineHeight: 1.5,
                        }}
                      >
                        <strong>{incident.scenario_id.replace("AI_NETRA_DEMO_00", "Incident ")}</strong>
                        {selected ? " — SELECTED" : ""}
                        <span style={{ display: "block", color: "#57534e" }}>{incident.building_id}</span>
                        <span style={{ display: "block" }}>
                          Reported: {incident.reported_people} people · {incident.reported_children} children · {incident.reported_seniors} seniors
                        </span>
                        <span style={{ display: "block" }}>
                          Depth {incident.reported_water_depth_m} m · Flow {incident.reported_flow_velocity_mps} m/s
                        </span>
                        <span style={{ display: "block", color: "#9a3412" }}>
                          Unverified synthetic report · Human review · No priority score
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
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
            <span>Historical mapped affected areas (2020)</span>
          </label>
          {showHistoricalFlood && (
            <div style={{ fontSize: 11, marginTop: 7, lineHeight: 1.5 }}>
              {historicalFloodLoading
                ? "Loading historical polygons..."
                : historicalFloodError
                  ? <span role="alert" style={{ color: "#b91c1c" }}>{historicalFloodError}</span>
                  : `${historicalFloodData?.features.length ?? 0} mapped polygons loaded`}
              <div style={{ display: "grid", gap: 5, marginTop: 8, color: "#334155" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span aria-hidden="true" style={{ width: 13, height: 13, background: "#38bdf8", border: "2px solid #0369a1", display: "inline-block", flexShrink: 0 }} />
                  <span>Blue: 7 generic flood-affected-area polygons (SymbolID 0)</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span aria-hidden="true" style={{ width: 13, height: 13, background: "#fbbf24", border: "2px solid #b45309", display: "inline-block", flexShrink: 0 }} />
                  <span>Amber: 2 named affected-locality polygons (SymbolID 3)</span>
                </div>
                <p style={{ color: "#92400e", margin: "3px 0 0" }}>
                  Neither category verifies building inundation or current flood risk.
                </p>
              </div>
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

          {/* HISTORICAL AFFECTED-AREA POLYGONS BY SOURCE CATEGORY */}
          {/* Keep this non-interactive and beneath selected buildings so map
              click identification and red building highlights remain usable. */}
          {showHistoricalFlood && historicalFloodData && (
            <GeoJSON
              key="historical-affected-areas-by-category-2020"
              data={historicalFloodData}
              interactive={false}
              style={(feature) => {
                const sourceIndex = Number(feature?.properties?.source_polygon_index);
                // Source provenance established in Step 9.1; do not infer
                // inundation from either original KML style classification.
                const isNamedLocality = sourceIndex === 13310 || sourceIndex === 13314;
                const isGenericFloodArea = [6125, 6137, 6207, 6218, 6221, 6237, 6358].includes(sourceIndex);
                if (isNamedLocality) {
                  return { color: "#b45309", weight: 2, fillColor: "#fbbf24", fillOpacity: 0.19 };
                }
                if (isGenericFloodArea) {
                  return { color: "#0369a1", weight: 2, fillColor: "#38bdf8", fillOpacity: 0.32 };
                }
                // Unexpected source feature: highly visible, never silently
                // classify as flood-affected or named locality.
                return { color: "#64748b", weight: 2, dashArray: "5 4", fillColor: "#94a3b8", fillOpacity: 0.12 };
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

          {/* THREE DISTINCT FICTIONAL EMERGENCY MARKERS */}
          {showSyntheticIncidents && syntheticIncidents.length > 0 && (
            <SyntheticIncidentLayer
              incidents={syntheticIncidents}
              selectedBuildingId={result?.match_type === "exact" ? result.building_id : undefined}
              onSelect={selectSyntheticIncident}
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
        selectedSyntheticIncident={selectedSyntheticIncident}
      />
    </div>
  );
}