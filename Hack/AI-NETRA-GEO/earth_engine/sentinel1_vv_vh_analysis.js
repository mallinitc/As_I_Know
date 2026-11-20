// ============================================================
// AI NETRA — STEP 8.76
// Sentinel-1 VV / VH Historical Radar Analysis
//
// Pilot: Moosarambagh — Musi River, Hyderabad
//
// CONTROL:
// 27 September 2020 → 09 October 2020
//
// EVENT:
// 09 October 2020 → 21 October 2020
//
// IMPORTANT:
// Radar changes are NOT confirmed flood detections.
// ============================================================


// ------------------------------------------------------------
// 1. PILOT AREA
// ------------------------------------------------------------

var pilot = ee.Geometry.Rectangle([
  78.50, 17.36,
  78.53, 17.38
]);

Map.centerObject(pilot, 14);

Map.addLayer(
  pilot,
  {color: "yellow"},
  "AI NETRA Pilot Area"
);


// ------------------------------------------------------------
// 2. SENTINEL-1 COLLECTION
// ------------------------------------------------------------

var s1 = ee.ImageCollection("COPERNICUS/S1_GRD")

  .filterBounds(pilot)

  .filterDate(
    "2020-09-20",
    "2020-11-01"
  )

  .filter(
    ee.Filter.eq(
      "instrumentMode",
      "IW"
    )
  )

  .filter(
    ee.Filter.eq(
      "orbitProperties_pass",
      "DESCENDING"
    )
  )

  .filter(
    ee.Filter.eq(
      "relativeOrbitNumber_start",
      165
    )
  )

  .filter(
    ee.Filter.listContains(
      "transmitterReceiverPolarisation",
      "VV"
    )
  )

  .filter(
    ee.Filter.listContains(
      "transmitterReceiverPolarisation",
      "VH"
    )
  );


// ------------------------------------------------------------
// 3. LOAD HISTORICAL IMAGES
// ------------------------------------------------------------

function getImage(date) {

  var image = ee.Image(

    s1.filterDate(
      date,
      ee.Date(date).advance(1, "day")
    ).first()

  );

  return image

    .select(["VV", "VH"])

    .focal_median(
      30,
      "circle",
      "meters"
    );

}


var sep27 = getImage("2020-09-27");

var oct09 = getImage("2020-10-09");

var oct21 = getImage("2020-10-21");


// ------------------------------------------------------------
// 4. CALCULATE RADAR CHANGES
// ------------------------------------------------------------

// Normal pre-event comparison

var control = oct09.subtract(sep27)

  .rename([
    "VV_change",
    "VH_change"
  ]);


// Event-period comparison

var event = oct21.subtract(oct09)

  .rename([
    "VV_change",
    "VH_change"
  ]);


// ------------------------------------------------------------
// 5. RADAR STATISTICS
// ------------------------------------------------------------

function getStats(image, label) {

  var stats = image.reduceRegion({

    reducer: ee.Reducer.mean()

      .combine({
        reducer2: ee.Reducer.minMax(),
        sharedInputs: true
      }),

    geometry: pilot,

    scale: 10,

    maxPixels: 1e8,

    tileScale: 4

  });

  print(label, stats);

}


getStats(
  control,
  "CONTROL — VV and VH"
);

getStats(
  event,
  "EVENT — VV and VH"
);


// ------------------------------------------------------------
// 6. RADAR CHANGE DISTRIBUTION
// ------------------------------------------------------------

function getDistribution(image, label) {

  var positive = image.gt(3);

  var negative = image.lt(-3);


  var positiveStats = positive.reduceRegion({

    reducer: ee.Reducer.mean(),

    geometry: pilot,

    scale: 10,

    maxPixels: 1e8,

    tileScale: 4

  });


  var negativeStats = negative.reduceRegion({

    reducer: ee.Reducer.mean(),

    geometry: pilot,

    scale: 10,

    maxPixels: 1e8,

    tileScale: 4

  });


  print(
    label + " — Positive change > +3 dB (%)",
    {

      VV: ee.Number(
        positiveStats.get("VV_change")
      ).multiply(100),

      VH: ee.Number(
        positiveStats.get("VH_change")
      ).multiply(100)

    }
  );


  print(
    label + " — Negative change < -3 dB (%)",
    {

      VV: ee.Number(
        negativeStats.get("VV_change")
      ).multiply(100),

      VH: ee.Number(
        negativeStats.get("VH_change")
      ).multiply(100)

    }
  );

}


getDistribution(
  control,
  "CONTROL"
);

getDistribution(
  event,
  "EVENT"
);


// ------------------------------------------------------------
// 7. VISUALIZATION
// ------------------------------------------------------------

var visualization = {

  min: -6,

  max: 6,

  palette: [
    "08306b",
    "4292c6",
    "ffffff",
    "fdae61",
    "b2182b"
  ]

};


Map.addLayer(

  event.select("VV_change").clip(pilot),

  visualization,

  "Event VV Radar Change",

  true

);


Map.addLayer(

  event.select("VH_change").clip(pilot),

  visualization,

  "Event VH Radar Change",

  false

);


// ------------------------------------------------------------
// 8. COMPLETION
// ------------------------------------------------------------

print(
  "AI NETRA — Sentinel-1 VV/VH analysis completed."
);

print(
  "Radar differences are not validated flood boundaries."
);