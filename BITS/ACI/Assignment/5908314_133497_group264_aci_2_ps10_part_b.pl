/* ------------------------------------------------------------
   Raisin Expert System — Web GUI with Tree Visualization
   
   ------------------------------------------------------------ */

:- use_module(library(http/thread_httpd)).
:- use_module(library(http/http_dispatch)).
:- use_module(library(http/http_parameters)).
:- use_module(library(http/html_write)).

:- http_handler(root(.), home_handler, []).

/* ------------------------- START SERVER ------------------------- */
start :-
    Port = 8000,
    http_server(http_dispatch,
                [ port(Port),
                  ip('127.0.0.1'),
                  workers(1)
                ]),
    format('~nRaisin web GUI running.~nOpen: http://127.0.0.1:~w/~n', [Port]),
    thread_get_message(_).  % keep main thread alive

/* ------------------------------ CSS ----------------------------- */
page_style -->
    {
      CSS = '
:root {
  --bg: #0f172a;          /* slate-900 */
  --card: #111827;        /* gray-900 */
  --muted: #9ca3af;       /* gray-400 */
  --text: #e5e7eb;        /* gray-200 */
  --accent: #60a5fa;      /* blue-400 */
  --accent-2: #22c55e;    /* green-500 */
  --chip: #1f2937;        /* gray-800 */
  --line: #334155;        /* slate-700 */
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  background: radial-gradient(1200px 800px at 20% 10%, #0b1220, var(--bg));
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, "Noto Sans", sans-serif;
  color: var(--text);
}
.wrap {
  max-width: 960px; margin: 28px auto; padding: 0 16px;
}
.header {
  margin-bottom: 16px;
}
.header h1 {
  font-size: 28px; margin: 0 0 6px 0;
}
.header p { margin: 0; color: var(--muted); }
.card {
  background: linear-gradient(180deg, #0b1220, var(--card));
  border: 1px solid #1f2937; border-radius: 16px;
  box-shadow: 0 10px 30px rgba(0,0,0,.35);
  padding: 18px;
}
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }

.form label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
.form input[type="text"] {
  width: 100%; padding: 10px 12px; border-radius: 10px;
  border: 1px solid #334155; background: #0b1220; color: var(--text);
  outline: none;
}
.form input[type="text"]::placeholder { color: #6b7280; }
.btnbar { display: flex; gap: 10px; margin-top: 12px; }
.btn {
  appearance: none; border: 1px solid #1d4ed8; color: white;
  background: linear-gradient(180deg, #1d4ed8, #1e40af);
  padding: 10px 14px; border-radius: 10px; cursor: pointer; font-weight: 600;
}
.btn.secondary {
  border: 1px solid #475569; color: var(--text);
  background: linear-gradient(180deg, #1f2937, #111827);
}
.badge {
  display: inline-block; padding: 4px 10px; border-radius: 999px;
  background: #0b1220; border: 1px solid #334155; color: var(--muted);
  font-size: 12px; margin-left: 8px;
}
.result {
  font-size: 20px; font-weight: 700; margin: 0 0 10px 0;
}
.result .cls { color: var(--accent-2); }
.caption { color: var(--muted); font-size: 13px; margin-top: 8px; }

/* ------- Tree layout (simple nested list with connector lines) ---- */
.tree { margin-top: 8px; }
.tree ul { list-style: none; padding-left: 28px; position: relative; margin: 0; }
.tree li {
  position: relative; margin: 10px 0 10px 0;
}
.tree li::before {
  content: ""; position: absolute; top: 14px; left: -16px; width: 16px;
  border-top: 1px solid var(--line);
}
.tree li::after {
  content: ""; position: absolute; top: -10px; left: -16px; height: 24px;
  border-left: 1px solid var(--line);
}
.tree li:first-child::after { top: 14px; height: 16px; }  /* trim first */
.tree li:last-child::after  { height: 14px; }              /* trim last */
.node {
  display: inline-block; padding: 8px 12px; border-radius: 10px;
  background: var(--chip); border: 1px solid #374151; font-size: 14px;
}
.node.true  { border-color: #2563eb; box-shadow: inset 0 0 0 1px rgba(96,165,250,.35); }
.node.leaf  { border-color: #16a34a; background: rgba(34,197,94,.08); }
.small-note { font-size: 12px; color: var(--muted); margin-top: 6px; }
'
    },
    html(style(CSS)).

/* ------------------------- PAGE BODY ---------------------------- */
home_handler(Request) :-
    http_parameters(Request,
        [ maj(MajA,   [optional(true)]),
          per(PerA,   [optional(true)]),
          ext(ExtA,   [optional(true)]),
          area(AreaA, [optional(true)]),
          ecc(EccA,   [optional(true)])
        ]),
    ( nonvar(MajA), nonvar(PerA), nonvar(ExtA), nonvar(AreaA), nonvar(EccA),
      atom_number(MajA, Maj),
      atom_number(PerA, Per),
      atom_number(ExtA, Ext),
      atom_number(AreaA, Area),
      atom_number(EccA, Ecc),
      classify_with_steps(Maj, Per, Ext, Area, Ecc, Class, Steps),
      steps_to_tree_dom(Steps, TreeLi),       % build nested <ul><li>… tree of the taken path
      TreeDOM = div(class(tree), ul([TreeLi])),
      Reply = result(Class, TreeDOM)
    ; Reply = no_input
    ),
    reply_html_page(
      [ title('Raisin Classifier — Pretty'),
        \page_style
      ],
      \page_content(Reply)
    ).

/* ------------- HTML content (form + result card) ---------------- */
page_content(no_input) -->
  html(div(class(wrap), [
    div(class(header), [
      h1('Raisin Classifier'), p('Enter the five features and press Classify.')
    ]),
    div(class(card), \form_block)
  ])).

page_content(result(Class, TreeDOM)) -->
  html(div(class(wrap), [
    div(class(header), [
      h1('Raisin Classifier'),
      p('Decision-tree classification with a visual path.')
    ]),
    div(class(grid), [
      div(class(card), \form_block),
      div(class(card), [
        div(class(result), ['Result: ', span(class(cls), Class),
                            span(class(badge), '4-in-a-row raisin types')]),
        div(class(caption), 'Taken path (root → leaf):'),
        TreeDOM,
        div(class('small-note'),
            'Green node is the leaf (final class). Blue outline shows the decisions along the way.')
      ])
    ])
  ])).

form_block -->
  html(div(class(form), [
    form([action='/', method='GET'], [
      \field('MajorAxisLength','maj','e.g., 410.0'),
      \field('Perimeter','per','e.g., 1100.0'),
      \field('Extent','ext','e.g., 0.72'),
      \field('Area','area','e.g., 60000'),
      \field('Eccentricity','ecc','e.g., 0.75'),
      div(class(btnbar), [
        input([type=submit, value='Classify', class=btn]),
        a([href='/', class='btn secondary'], 'Clear')
      ])
    ])
  ])).

field(Label, Name, Placeholder) -->
  html(div([
    label([for=Name], Label),
    input([type='text', name=Name, placeholder=Placeholder])
  ])).

/* ------------- Convert step list → nested tree DOM --------------- */
/* Steps is like:
   [ 'MajorAxisLength =< ...',
     'Perimeter > ...',
     ...,
     'LEAF: Kecimen'
   ]
   We turn it into nested <ul><li>…</li></ul> where each step nests the next.
*/
steps_to_tree_dom([S], li(div(class('node leaf'), S))).   % leaf node (green)

steps_to_tree_dom([S|Rest], li([div(class('node true'), S), ul([Child])])) :-
    steps_to_tree_dom(Rest, Child).

/* ---------------- Decision tree (exact thresholds) ---------------- */
classify_with_steps(Maj, Per, Ext, Area, Ecc, Class, Steps) :-
    ( Maj =< 422.279133 ->
        S1 = 'MajorAxisLength <= 422.279133 (TRUE)',
        ( Per =< 1006.375 ->
            Steps = [S1, 'Perimeter <= 1006.375 (TRUE) -> LEAF: Kecimen'],
            Class = 'Kecimen'
        ;   S2 = 'Perimeter > 1006.375 (TRUE)',
            ( Ext =< 0.7476 ->
                S3 = 'Extent <= 0.7476 (TRUE)',
                ( Per =< 1122.831 ->
                    S4 = 'Perimeter <= 1122.831 (TRUE)',
                    ( Area =< 62835 ->
                        S5 = 'Area <= 62835 (TRUE)',
                        ( Ext =< 0.701678 ->
                            S6 = 'Extent <= 0.701678 (TRUE)',
                            ( Ext =< 0.666255 ->
                                Steps = [S1,S2,S3,S4,S5,S6,'Extent <= 0.666255 (TRUE) -> LEAF: Besni'],
                                Class = 'Besni'
                            ;   Steps = [S1,S2,S3,S4,S5,S6,'Extent > 0.666255 (TRUE) -> LEAF: Kecimen'],
                                Class = 'Kecimen'
                            )
                        ;   Steps = [S1,S2,S3,S4,S5,'Extent > 0.701678 (TRUE) -> LEAF: Besni'],
                            Class = 'Besni'
                        )
                    ;   Steps = [S1,S2,S3,S4,'Area > 62835 (TRUE) -> LEAF: Kecimen'],
                        Class = 'Kecimen'
                    )
                ;   S4b = 'Perimeter > 1122.831 (TRUE)',
                    ( Ext =< 0.671309 ->
                        Steps = [S1,S2,S3,S4b,'Extent <= 0.671309 (TRUE) -> LEAF: Besni'],
                        Class = 'Besni'
                    ;   S5b = 'Extent > 0.671309 (TRUE)',
                        ( Ecc =< 0.75951 ->
                            Steps = [S1,S2,S3,S4b,S5b,'Eccentricity <= 0.75951 (TRUE) -> LEAF: Besni'],
                            Class = 'Besni'
                        ;   Steps = [S1,S2,S3,S4b,S5b,'Eccentricity > 0.75951 (TRUE) -> LEAF: Kecimen'],
                            Class = 'Kecimen'
                        )
                    )
                )
            ;   Steps = [S1,S2,'Extent > 0.7476 (TRUE) -> LEAF: Kecimen'],
                Class = 'Kecimen'
            )
        )
    ;   Steps = ['MajorAxisLength > 422.279133 (TRUE) -> LEAF: Besni'],
        Class = 'Besni'
    ).
