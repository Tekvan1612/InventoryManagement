 function fullCalender() {
            /* initialize the external events
              -----------------------------------------------------------------*/

            var containerEl = document.getElementById('external-events');
            if ($('#external-events').length > 0) {
                new FullCalendar.Draggable(containerEl, {
                    itemSelector: '.external-event',
                    eventData: function (eventEl) {
                        return {
                            title: eventEl.innerText.trim()
                        }
                    }
                });
            }

            /* initialize the calendar
              -----------------------------------------------------------------*/

            var calendarEl = document.getElementById('calendar');
            var currentDate = new Date();  // Get the current date

            var calendar = new FullCalendar.Calendar(calendarEl, {
                headerToolbar: {
                    left: 'prev,next today',
                    center: 'title',
                    right: 'dayGridMonth,timeGridWeek,timeGridDay'
                },
                initialView: 'dayGridMonth',
                initialDate: currentDate.toISOString().substring(0, 10),  // Ensure correct date format YYYY-MM-DD
                selectable: true,
                selectMirror: true,
                select: function (arg) {
                    // Show modal
                    $('#eventModal').modal('show');

                    // Set start and end date inputs
                    $('#eventStart').val(arg.startStr);
                    $('#eventEnd').val(arg.endStr);

                    // Show or hide start/end date fields based on selection
                    if (arg.startStr === arg.endStr) {
                        $('#eventStartEndGroup').hide();
                    } else {
                        $('#eventStartEndGroup').show();
                    }

                    // Save event on button click
                    $('#saveEvent').off('click').on('click', function () {
                        var title = $('#eventTitle').val();
                        var description = $('#eventDescription').val();
                        var location = $('#eventLocation').val();
                        var start = $('#eventStart').val();
                        var end = $('#eventEnd').val();

                        if (title) {
                            calendar.addEvent({
                                title: title,
                                start: arg.startStr,
                                end: arg.endStr,
                                allDay: arg.allDay,
                                extendedProps: {
                                    description: description,
                                    location: location
                                }
                            });
                            $('#eventForm')[0].reset();
                            $('#eventModal').modal('hide');
                        }
                    });

                    calendar.unselect();
                },
                editable: true,
                droppable: true, // this allows things to be dropped onto the calendar
                drop: function (arg) {
                    // is the "remove after drop" checkbox checked?
                    if (document.getElementById('drop-remove').checked) {
                        // if so, remove the element from the "Draggable Events" list
                        arg.draggedEl.parentNode.removeChild(arg.draggedEl);
                    }
                },
                weekNumbers: true,
                navLinks: true, // can click day/week names to navigate views
                nowIndicator: true,
                events: [
                    {
                        title: 'All Day Event',
                        start: '2021-02-01'
                    },
                    {
                        title: 'Long Event',
                        start: '2021-02-07',
                        end: '2021-02-10',
                        className: "bg-danger"
                    },
                    {
                        groupId: 999,
                        title: 'Repeating Event',
                        start: '2021-02-09T16:00:00'
                    },
                    {
                        groupId: 999,
                        title: 'Repeating Event',
                        start: '2021-02-16T16:00:00'
                    },
                    {
                        title: 'Conference',
                        start: '2021-02-11',
                        end: '2021-02-13',
                        className: "bg-danger"
                    },
                    {
                        title: 'Lunch',
                        start: '2021-02-12T12:00:00'
                    },
                    {
                        title: 'Meeting',
                        start: '2021-04-12T14:30:00'
                    },
                    {
                        title: 'Happy Hour',
                        start: '2021-07-12T17:30:00'
                    },
                    {
                        title: 'Dinner',
                        start: '2021-02-12T20:00:00',
                        className: "bg-warning"
                    },
                    {
                        title: 'Birthday Party',
                        start: '2021-02-13T07:00:00',
                        className: "bg-secondary"
                    },
                    {
                        title: 'Click for Google',
                        url: 'http://google.com/',
                        start: '2021-02-28'
                    }
                ],
                eventDidMount: function (info) {
                    // Customize the tooltip content to show extendedProps
                    if (info.event.extendedProps.description) {
                        var tooltipContent = 'Description: ' + info.event.extendedProps.description + '<br>';
                        if (info.event.extendedProps.location) {
                            tooltipContent += 'Location: ' + info.event.extendedProps.location;
                        }
                        var tooltip = new Tooltip(info.el, {
                            title: tooltipContent,
                            html: true,
                            placement: 'top',
                            trigger: 'hover',
                            container: 'body'
                        });
                    }
                }
            });
            calendar.render();
        }

        jQuery(window).on('load', function () {
            setTimeout(function () {
                fullCalender();
            }, 1000);
        });